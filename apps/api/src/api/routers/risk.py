"""Risk limits per paper/live account and the kill switch (ADR-007)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, State, User
from core.calendar import nse_calendar
from core.db.models import KillSwitchEvent, PaperAccount, RiskLimit
from core.db.models._enums import ActorType, KillSwitchAction, KillSwitchScope, RiskLimitScope
from core.time import utcnow
from risk.kill_switch import KillSwitch
from risk.limits import RiskLimits

router = APIRouter(prefix="/risk", tags=["risk"])


class LimitsOut(BaseModel):
    scope: RiskLimitScope
    scope_id: int
    version: int
    effective_from: datetime | None
    limits: RiskLimits
    is_default: bool
    edit_locked: bool
    edit_lock_reason: str | None


class KillStatus(BaseModel):
    scope: str
    active: bool
    detail: dict[str, Any] | None


class KillIn(BaseModel):
    reason: str
    flatten: bool = False


def _edit_lock(now: datetime) -> tuple[bool, str | None]:
    """Risk limits can only be changed outside market hours (discipline rule from the
    design discussion: limits change weekly, never mid-session)."""
    cal = nse_calendar()
    if cal.is_open(now):
        return True, "market is open; limits can be edited after 15:30 IST"
    return False, None


async def _active_limits(db: DB, scope: RiskLimitScope, scope_id: int) -> RiskLimit | None:
    res = await db.execute(
        select(RiskLimit).where(
            RiskLimit.scope == scope, RiskLimit.scope_id == scope_id, RiskLimit.is_active.is_(True)
        )
    )
    return res.scalar_one_or_none()


async def load_limits(db: DB, scope: RiskLimitScope, scope_id: int) -> RiskLimits:
    row = await _active_limits(db, scope, scope_id)
    return RiskLimits.model_validate(row.limits) if row else RiskLimits()


@router.get("/limits/paper/{account_id}", response_model=LimitsOut)
async def get_paper_limits(account_id: int, db: DB, user: User) -> LimitsOut:
    a = await db.get(PaperAccount, account_id)
    if a is None or a.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper account not found")
    row = await _active_limits(db, RiskLimitScope.PAPER_ACCOUNT, account_id)
    locked, why = _edit_lock(utcnow())
    return LimitsOut(
        scope=RiskLimitScope.PAPER_ACCOUNT,
        scope_id=account_id,
        version=row.version if row else 0,
        effective_from=row.effective_from if row else None,
        limits=RiskLimits.model_validate(row.limits) if row else RiskLimits(),
        is_default=row is None,
        edit_locked=locked,
        edit_lock_reason=why,
    )


@router.put("/limits/paper/{account_id}", response_model=LimitsOut)
async def put_paper_limits(account_id: int, body: RiskLimits, db: DB, user: User) -> LimitsOut:
    a = await db.get(PaperAccount, account_id)
    if a is None or a.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper account not found")
    locked, why = _edit_lock(utcnow())
    if locked:
        raise HTTPException(status.HTTP_423_LOCKED, why)
    prev = await _active_limits(db, RiskLimitScope.PAPER_ACCOUNT, account_id)
    if prev is not None:
        prev.is_active = False
    row = RiskLimit(
        user_id=user.user_id,
        scope=RiskLimitScope.PAPER_ACCOUNT,
        scope_id=account_id,
        limits=body.model_dump(mode="json"),
        version=(prev.version + 1) if prev else 1,
        effective_from=utcnow(),
        created_by=user.user_id,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="risk.limits.update",
        entity_type="risk_limits",
        entity_id=row.id,
        before=prev.limits if prev else None,
        after=row.limits,
    )
    await db.commit()
    return await get_paper_limits(account_id, db, user)


# ---------------------------------------------------------------- kill switch
def _scope_str(scope: KillSwitchScope, scope_id: int | None) -> str:
    return "global" if scope == KillSwitchScope.GLOBAL else f"{scope.value}:{scope_id}"


@router.get("/kill-switch", response_model=list[KillStatus])
async def kill_status(
    state: State, _: User, account_id: int | None = None, strategy_id: int | None = None
) -> list[KillStatus]:
    ks = KillSwitch(state.redis)
    scopes = ["global"]
    if account_id is not None:
        scopes.append(f"account:{account_id}")
    if strategy_id is not None:
        scopes.append(f"strategy:{strategy_id}")
    return [
        KillStatus(scope=s, active=await ks.is_active(s), detail=await ks.status(s)) for s in scopes
    ]


@router.post("/kill-switch/{scope}", response_model=KillStatus)
async def kill_activate(
    scope: KillSwitchScope,
    body: KillIn,
    db: DB,
    state: State,
    user: User,
    scope_id: int | None = None,
) -> KillStatus:
    """Anyone with a session can STOP trading. Deactivation needs the owner role."""
    if scope != KillSwitchScope.GLOBAL and scope_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "scope_id required")
    ks = KillSwitch(state.redis)
    s = _scope_str(scope, scope_id)
    ev = await ks.activate(s, body.reason + (" [flatten]" if body.flatten else ""), user.email)
    db.add(
        KillSwitchEvent(
            scope=scope,
            scope_id=scope_id,
            action=KillSwitchAction.ACTIVATE,
            reason=body.reason,
            triggered_by=user.user_id,
            actor_type=ActorType.USER,
            positions_flattened=body.flatten,
            ts=utcnow(),
        )
    )
    await audit(
        db,
        user_id=user.user_id,
        action="kill_switch.activate",
        entity_type="kill_switch",
        entity_id=s,
        reason=body.reason,
        after=ev,
    )
    await db.commit()
    await state.notifier.send(
        f"KILL SWITCH ON ({s}) by {user.email}: {body.reason}", level="critical"
    )
    return KillStatus(scope=s, active=True, detail=await ks.status(s))


@router.delete("/kill-switch/{scope}", response_model=KillStatus)
async def kill_deactivate(
    scope: KillSwitchScope,
    body: KillIn,
    db: DB,
    state: State,
    user: User,
    scope_id: int | None = None,
) -> KillStatus:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can clear a kill switch")
    ks = KillSwitch(state.redis)
    s = _scope_str(scope, scope_id)
    ev = await ks.deactivate(s, body.reason, user.email)
    db.add(
        KillSwitchEvent(
            scope=scope,
            scope_id=scope_id,
            action=KillSwitchAction.DEACTIVATE,
            reason=body.reason,
            triggered_by=user.user_id,
            actor_type=ActorType.USER,
            positions_flattened=False,
            ts=utcnow(),
        )
    )
    await audit(
        db,
        user_id=user.user_id,
        action="kill_switch.deactivate",
        entity_type="kill_switch",
        entity_id=s,
        reason=body.reason,
        after=ev,
    )
    await db.commit()
    await state.notifier.send(
        f"Kill switch cleared ({s}) by {user.email}: {body.reason}", level="warning"
    )
    return KillStatus(scope=s, active=False, detail=None)


@router.get("/kill-switch/events", response_model=list[dict[str, Any]])
async def kill_events(db: DB, _: User, limit: int = 50) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(KillSwitchEvent).order_by(KillSwitchEvent.ts.desc()).limit(limit)
    )
    return [
        {
            "id": e.id,
            "scope": e.scope.value,
            "scope_id": e.scope_id,
            "action": e.action.value,
            "reason": e.reason,
            "triggered_by": e.triggered_by,
            "actor_type": e.actor_type.value,
            "positions_flattened": e.positions_flattened,
            "ts": e.ts.isoformat(),
        }
        for e in rows.scalars().all()
    ]
