"""Trading protocols (Mark 1 Stage 3.1): named, versioned bundles of registered actions.

This router validates, stores and enqueues; the worker executes runs (CLAUDE.md: no long
work inside a request). Definitions are JSON only and validated against the action registry
(CLAUDE.md rule 4). No action can place, modify or cancel an order.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, CurrentUser, State, User
from core.db.models import Protocol, ProtocolRun
from core.logging import get_logger
from core.time import utcnow
from protocols import REGISTRY
from protocols.builtin import BUILTIN_CODES
from protocols.registry import ProtocolSpec, StepSpec
from protocols.service import (
    ProtocolError,
    cancel_run,
    check_spec,
    confirm_run,
    create_run,
    describe_steps,
    get_protocol,
    list_protocols,
    protocol_risk,
    seed_builtins,
    stored_steps,
)

router = APIRouter(prefix="/protocols", tags=["protocols"])
log = get_logger(__name__)

_seeded = False


def _require_owner(user: CurrentUser) -> None:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can do this")


# ---------------------------------------------------------------- schemas
class StepOut(BaseModel):
    tool: str
    args: dict[str, Any]
    on_error: str
    risk: str


class ProtocolOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    domain: str
    version: int
    steps: list[StepOut]
    layout: dict[str, Any] | None
    confirm_required: bool
    is_builtin: bool
    editable: bool
    max_risk: str
    updated_at: datetime


class ActionOut(BaseModel):
    name: str
    description: str
    risk: str
    args_schema: dict[str, Any]


class ProtocolBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    steps: list[dict[str, Any]] = Field(min_length=1)
    layout: dict[str, Any] | None = None
    confirm_required: bool = False


class ProtocolCreate(ProtocolBody):
    code: str


class RunIn(BaseModel):
    trigger: Literal["button", "api"] = "button"


class RunOut(BaseModel):
    id: int
    protocol_id: int
    protocol_code: str
    protocol_name: str
    protocol_version: int
    user_id: int | None
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    steps: list[dict[str, Any]]
    summary: str | None


class CancelIn(BaseModel):
    reason: str = Field(default="cancelled by user", min_length=3, max_length=200)


# ---------------------------------------------------------------- helpers
async def _ensure_seeded(db: DB) -> None:
    global _seeded
    if _seeded:
        return
    result = await seed_builtins(db)
    await db.commit()
    _seeded = True
    log.info("protocols.seeded", result=result)


def _out(p: Protocol) -> ProtocolOut:
    return ProtocolOut(
        id=p.id,
        code=p.code,
        name=p.name,
        description=p.description,
        domain=p.domain,
        version=p.version,
        steps=[StepOut(**s) for s in describe_steps(p)],
        layout=p.layout,
        confirm_required=p.confirm_required,
        is_builtin=p.is_builtin,
        editable=not p.is_builtin,
        max_risk=protocol_risk(p),
        updated_at=p.updated_at,
    )


def _run_out(r: ProtocolRun, p: Protocol) -> RunOut:
    return RunOut(
        id=r.id,
        protocol_id=r.protocol_id,
        protocol_code=p.code,
        protocol_name=p.name,
        protocol_version=r.protocol_version,
        user_id=r.user_id,
        trigger=r.trigger,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        steps=r.steps,
        summary=r.summary,
    )


def _spec(code: str, body: ProtocolBody) -> ProtocolSpec:
    try:
        spec = ProtocolSpec(
            code=code,
            name=body.name,
            description=body.description,
            steps=[StepSpec.model_validate(s) for s in body.steps],
            layout=body.layout,
            confirm_required=body.confirm_required,
        )
        check_spec(spec)
    except ValidationError as exc:
        msgs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(msgs)) from exc
    except ProtocolError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return spec


def _snapshot(p: Protocol) -> dict[str, Any]:
    return {
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "version": p.version,
        "steps": p.steps,
        "layout": p.layout,
        "confirm_required": p.confirm_required,
    }


async def _owned_editable(db: DB, code: str, user: CurrentUser) -> Protocol:
    p = await get_protocol(db, code)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "protocol not found")
    if p.is_builtin:
        raise HTTPException(status.HTTP_409_CONFLICT, "built-in protocols cannot be changed")
    if p.user_id is not None and p.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "protocol not found")
    return p


async def _enqueue(state: State, run_id: int) -> None:
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job("run_protocol", run_id, _job_id=f"protocol_run:{run_id}")
    finally:
        await pool.aclose()


async def _enqueue_or_fail(db: DB, state: State, run: ProtocolRun) -> None:
    try:
        await _enqueue(state, run.id)
    except Exception as exc:
        log.error("protocols.enqueue_failed", run=run.id, error=str(exc))
        run.status = "failed"
        run.finished_at = utcnow()
        run.summary = "could not reach the worker queue (Redis); nothing was executed"
        await db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, run.summary) from exc


async def _run_and_protocol(db: DB, run_id: int, user: CurrentUser) -> tuple[ProtocolRun, Protocol]:
    r = await db.get(ProtocolRun, run_id)
    if r is None or (r.user_id is not None and r.user_id != user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    p = await db.get(Protocol, r.protocol_id)
    assert p is not None
    return r, p


# ---------------------------------------------------------------- definitions
@router.get("", response_model=list[ProtocolOut])
async def protocols_list(db: DB, user: User) -> list[ProtocolOut]:
    await _ensure_seeded(db)
    return [_out(p) for p in await list_protocols(db, user.user_id)]


@router.get("/actions", response_model=list[ActionOut])
async def actions_catalogue(_: User) -> list[ActionOut]:
    return [ActionOut(**a) for a in REGISTRY.catalogue()]


@router.post("", response_model=ProtocolOut, status_code=status.HTTP_201_CREATED)
async def protocol_create(body: ProtocolCreate, db: DB, user: User) -> ProtocolOut:
    _require_owner(user)
    await _ensure_seeded(db)
    spec = _spec(body.code, body)
    if spec.code in BUILTIN_CODES or await get_protocol(db, spec.code) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"protocol {spec.code!r} already exists")
    p = Protocol(
        code=spec.code,
        name=spec.name,
        description=spec.description,
        domain="trading",
        version=1,
        steps=stored_steps(spec),
        layout=spec.layout,
        confirm_required=spec.confirm_required,
        is_builtin=False,
        user_id=user.user_id,
    )
    db.add(p)
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="protocol.create",
        entity_type="protocol",
        entity_id=p.id,
        after=_snapshot(p),
    )
    await db.commit()
    await db.refresh(p)
    return _out(p)


@router.put("/{code}", response_model=ProtocolOut)
async def protocol_update(code: str, body: ProtocolBody, db: DB, user: User) -> ProtocolOut:
    _require_owner(user)
    p = await _owned_editable(db, code, user)
    spec = _spec(code, body)
    before = _snapshot(p)
    p.name = spec.name
    p.description = spec.description
    p.steps = stored_steps(spec)
    p.layout = spec.layout
    p.confirm_required = spec.confirm_required
    p.version += 1
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="protocol.update",
        entity_type="protocol",
        entity_id=p.id,
        before=before,
        after=_snapshot(p),
    )
    await db.commit()
    await db.refresh(p)
    return _out(p)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def protocol_delete(code: str, db: DB, user: User) -> None:
    _require_owner(user)
    p = await _owned_editable(db, code, user)
    await audit(
        db,
        user_id=user.user_id,
        action="protocol.delete",
        entity_type="protocol",
        entity_id=p.id,
        before=_snapshot(p),
    )
    await db.delete(p)
    await db.commit()


# ---------------------------------------------------------------- runs
@router.post("/{code}/run", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def protocol_run(code: str, body: RunIn, db: DB, state: State, user: User) -> RunOut:
    await _ensure_seeded(db)
    p = await get_protocol(db, code)
    if p is None or (p.user_id is not None and p.user_id != user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "protocol not found")
    try:
        run = await create_run(db, p, user_id=user.user_id, trigger=body.trigger)
    except ProtocolError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="protocol.run",
        entity_type="protocol_run",
        entity_id=run.id,
        after={"protocol": p.code, "version": p.version, "status": run.status},
    )
    await db.commit()
    if run.status == "running":
        await _enqueue_or_fail(db, state, run)
    return _run_out(run, p)


@router.get("/runs", response_model=list[RunOut])
async def runs_list(
    db: DB,
    user: User,
    code: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RunOut]:
    q = (
        select(ProtocolRun, Protocol)
        .join(Protocol, Protocol.id == ProtocolRun.protocol_id)
        .where((ProtocolRun.user_id == user.user_id) | ProtocolRun.user_id.is_(None))
        .order_by(ProtocolRun.started_at.desc(), ProtocolRun.id.desc())
        .limit(limit)
    )
    if code:
        q = q.where(Protocol.code == code)
    return [_run_out(r, p) for r, p in (await db.execute(q)).all()]


@router.get("/runs/{run_id}", response_model=RunOut)
async def run_get(run_id: int, db: DB, user: User) -> RunOut:
    r, p = await _run_and_protocol(db, run_id, user)
    return _run_out(r, p)


@router.post("/runs/{run_id}/confirm", response_model=RunOut)
async def run_confirm(run_id: int, db: DB, state: State, user: User) -> RunOut:
    _require_owner(user)
    r, p = await _run_and_protocol(db, run_id, user)
    try:
        await confirm_run(db, r)
    except ProtocolError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="protocol.run.confirm",
        entity_type="protocol_run",
        entity_id=r.id,
        after={"protocol": p.code, "steps": [s["tool"] for s in r.steps]},
    )
    await db.commit()
    await _enqueue_or_fail(db, state, r)
    return _run_out(r, p)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def run_cancel(run_id: int, body: CancelIn, db: DB, user: User) -> RunOut:
    r, p = await _run_and_protocol(db, run_id, user)
    try:
        await cancel_run(db, r, body.reason)
    except ProtocolError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="protocol.run.cancel",
        entity_type="protocol_run",
        entity_id=r.id,
        reason=body.reason,
    )
    await db.commit()
    return _run_out(r, p)
