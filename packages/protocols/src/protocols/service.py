"""Protocols in the database: seeding built-ins, owner CRUD validation, creating runs,
executing them (worker), confirming and cancelling.

Run lifecycle (`protocol_runs.status`):
  awaiting_confirmation --confirm--> running --worker--> succeeded | partial | failed
  awaiting_confirmation | running --cancel--> cancelled
A run stores its planned steps when it is created; the worker executes exactly that plan,
so what the owner confirmed is what runs even if the protocol is edited meanwhile.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Protocol, ProtocolRun
from core.logging import get_logger
from core.time import utcnow
from protocols.actions import REGISTRY
from protocols.builtin import BUILTINS
from protocols.context import ActionContext
from protocols.registry import ActionRegistry, ProtocolSpec, StepSpec, max_risk, validate_steps
from protocols.runner import RunOutcome, execute_steps, plan

log = get_logger(__name__)

OPEN_STATUSES = ("running", "awaiting_confirmation")


class ProtocolError(Exception):
    """A request that cannot be honoured (invalid definition, wrong run state)."""


def stored_steps(spec: ProtocolSpec) -> list[dict[str, Any]]:
    return [s.model_dump() for s in spec.steps]


def steps_of(p: Protocol) -> list[StepSpec]:
    return [StepSpec.model_validate(s) for s in p.steps]


def check_spec(spec: ProtocolSpec, registry: ActionRegistry = REGISTRY) -> None:
    errors = validate_steps(spec.steps, spec.confirm_required, registry)
    if errors:
        raise ProtocolError("; ".join(errors))


def describe_steps(p: Protocol, registry: ActionRegistry = REGISTRY) -> list[dict[str, Any]]:
    out = []
    for s in steps_of(p):
        spec = registry.get(s.tool)
        out.append({**s.model_dump(), "risk": spec.risk if spec else "unknown"})
    return out


def protocol_risk(p: Protocol, registry: ActionRegistry = REGISTRY) -> str:
    return max_risk(steps_of(p), registry)


# ----------------------------------------------------------------------------- seeding
async def seed_builtins(db: AsyncSession) -> dict[str, str]:
    """Insert missing built-ins, update changed ones with version + 1. Idempotent and safe
    to run concurrently (insert ... on conflict do nothing). The caller commits."""
    result: dict[str, str] = {}
    for spec in BUILTINS:
        check_spec(spec)
        values = {
            "name": spec.name,
            "description": spec.description,
            "steps": stored_steps(spec),
            "layout": spec.layout,
            "confirm_required": spec.confirm_required,
        }
        ins = (
            insert(Protocol)
            .values(code=spec.code, domain="trading", version=1, is_builtin=True, **values)
            .on_conflict_do_nothing(index_elements=["code"])
            .returning(Protocol.id)
        )
        if (await db.execute(ins)).scalar_one_or_none() is not None:
            result[spec.code] = "created"
            continue
        row = (await db.execute(select(Protocol).where(Protocol.code == spec.code))).scalar_one()
        if not row.is_builtin:
            result[spec.code] = "skipped: owner protocol uses this code"
            continue
        current = {
            "name": row.name,
            "description": row.description,
            "steps": row.steps,
            "layout": row.layout,
            "confirm_required": row.confirm_required,
        }
        if current == values:
            result[spec.code] = "unchanged"
            continue
        for k, v in values.items():
            setattr(row, k, v)
        row.version += 1
        result[spec.code] = f"updated to v{row.version}"
    await db.flush()
    return result


# ----------------------------------------------------------------------------- reads
async def list_protocols(db: AsyncSession, user_id: int | None) -> list[Protocol]:
    q = select(Protocol).order_by(Protocol.is_builtin.desc(), Protocol.code)
    if user_id is not None:
        q = q.where(or_(Protocol.is_builtin.is_(True), Protocol.user_id == user_id))
    return list((await db.execute(q)).scalars().all())


async def get_protocol(db: AsyncSession, code: str) -> Protocol | None:
    return (await db.execute(select(Protocol).where(Protocol.code == code))).scalar_one_or_none()


# ----------------------------------------------------------------------------- runs
async def create_run(
    db: AsyncSession, p: Protocol, *, user_id: int | None, trigger: str
) -> ProtocolRun:
    steps = steps_of(p)
    errors = validate_steps(steps, p.confirm_required, REGISTRY)
    if errors:
        raise ProtocolError("protocol no longer valid: " + "; ".join(errors))
    run = ProtocolRun(
        protocol_id=p.id,
        protocol_version=p.version,
        user_id=user_id,
        trigger=trigger,
        status="awaiting_confirmation" if p.confirm_required else "running",
        started_at=utcnow(),
        steps=plan(steps),
    )
    db.add(run)
    await db.flush()
    return run


async def confirm_run(db: AsyncSession, run: ProtocolRun) -> None:
    if run.status != "awaiting_confirmation":
        raise ProtocolError(f"run is {run.status}, not awaiting confirmation")
    res = await db.execute(
        update(ProtocolRun)
        .where(ProtocolRun.id == run.id, ProtocolRun.status == "awaiting_confirmation")
        .values(status="running")
    )
    if getattr(res, "rowcount", 1) != 1:
        raise ProtocolError("run changed state meanwhile")
    run.status = "running"


async def cancel_run(db: AsyncSession, run: ProtocolRun, reason: str = "cancelled") -> None:
    if run.status not in OPEN_STATUSES:
        raise ProtocolError(f"run is {run.status}; only open runs can be cancelled")
    now = utcnow()
    await db.execute(
        update(ProtocolRun)
        .where(ProtocolRun.id == run.id, ProtocolRun.status.in_(OPEN_STATUSES))
        .values(status="cancelled", finished_at=now, summary=reason)
    )
    run.status = "cancelled"
    run.finished_at = now
    run.summary = reason


async def execute_run(
    db: AsyncSession,
    run_id: int,
    make_ctx: Callable[[ProtocolRun], ActionContext],
    registry: ActionRegistry = REGISTRY,
) -> RunOutcome | None:
    """Execute a `running` run whose steps have not started. Commits after every step so the
    UI sees progress; a cancel is honoured between steps. Returns None when there is nothing
    to do (not found, not running, or already executed by an earlier delivery)."""
    run = (
        await db.execute(select(ProtocolRun).where(ProtocolRun.id == run_id).with_for_update())
    ).scalar_one_or_none()
    if run is None or run.status != "running":
        return None
    if any(s.get("status") != "pending" for s in run.steps):
        return None
    ctx = make_ctx(run)

    async def progress(results: list[dict[str, Any]]) -> None:
        await db.execute(
            update(ProtocolRun).where(ProtocolRun.id == run_id).values(steps=list(results))
        )
        await db.commit()

    async def cancelled() -> bool:
        st = (
            await db.execute(select(ProtocolRun.status).where(ProtocolRun.id == run_id))
        ).scalar_one()
        return bool(st == "cancelled")

    outcome = await execute_steps(
        run.steps, registry, ctx, is_cancelled=cancelled, on_progress=progress
    )
    values: dict[str, Any] = {"steps": outcome.steps, "finished_at": utcnow()}
    if outcome.status != "cancelled":
        values.update(status=outcome.status, summary=outcome.summary)
    await db.execute(
        update(ProtocolRun)
        .where(ProtocolRun.id == run_id, ProtocolRun.status != "cancelled")
        .values(**values)
    )
    if outcome.status == "cancelled":
        await db.execute(
            update(ProtocolRun).where(ProtocolRun.id == run_id).values(steps=outcome.steps)
        )
    await db.commit()
    log.info("protocol.run_done", run=run_id, status=outcome.status)
    return outcome
