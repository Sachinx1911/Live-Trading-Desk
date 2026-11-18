"""Strategy library: strategies, immutable versions, status transitions, activations.

The DSL itself is validated by `strategy.dsl`; this router never executes anything.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from api.audit import audit
from api.deps import DB, User
from core.db.models import Strategy, StrategyApproval, StrategyVersion
from core.db.models._enums import (
    CreatedBy,
    Decision,
    StrategyCategory,
    StrategyOrigin,
    StrategyVersionStatus,
)
from core.time import utcnow

router = APIRouter(prefix="/strategies", tags=["strategies"])

# Allowed user-driven transitions (ADR: AI may only create drafts; approvals are user acts).
TRANSITIONS: dict[StrategyVersionStatus, set[StrategyVersionStatus]] = {
    StrategyVersionStatus.DRAFT: {StrategyVersionStatus.BACKTESTED, StrategyVersionStatus.REJECTED},
    StrategyVersionStatus.BACKTESTED: {
        StrategyVersionStatus.VALIDATED,
        StrategyVersionStatus.PAPER,
        StrategyVersionStatus.REJECTED,
    },
    StrategyVersionStatus.VALIDATED: {StrategyVersionStatus.PAPER, StrategyVersionStatus.REJECTED},
    StrategyVersionStatus.PAPER: {
        StrategyVersionStatus.APPROVED_LIVE,
        StrategyVersionStatus.RETIRED,
    },
    StrategyVersionStatus.APPROVED_LIVE: {StrategyVersionStatus.RETIRED},
    StrategyVersionStatus.RETIRED: set(),
    StrategyVersionStatus.REJECTED: set(),
}
# Phase 3: paper trading needs at least a DRAFT that validates; backtest gate arrives in Phase 4.
PAPER_ELIGIBLE = {
    StrategyVersionStatus.DRAFT,
    StrategyVersionStatus.BACKTESTED,
    StrategyVersionStatus.VALIDATED,
    StrategyVersionStatus.PAPER,
}


class StrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: StrategyCategory = StrategyCategory.OTHER
    origin: StrategyOrigin = StrategyOrigin.USER_VISUAL
    description: str | None = None
    tags: list[str] = []


class VersionIn(BaseModel):
    dsl: dict[str, Any]
    source_text: str | None = None
    source_language: str | None = None
    change_summary: str | None = None
    parent_version_id: int | None = None


class ValidationOut(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
    missing_information: list[str]


class VersionOut(BaseModel):
    id: int
    strategy_id: int
    version_no: int
    parent_version_id: int | None
    status: StrategyVersionStatus
    dsl: dict[str, Any]
    dsl_schema_version: str
    dsl_hash: str
    source_text: str | None
    source_language: str | None
    created_by: CreatedBy
    change_summary: str | None
    created_at: datetime
    frozen_at: datetime | None
    validation: ValidationOut | None = None


class StrategyOut(BaseModel):
    id: int
    name: str
    category: StrategyCategory
    origin: StrategyOrigin
    description: str | None
    tags: list[str]
    is_archived: bool
    created_at: datetime
    latest_version: VersionOut | None


class TransitionIn(BaseModel):
    to_status: StrategyVersionStatus
    note: str | None = None
    evidence: dict[str, Any] = {}


def _validate(dsl: dict[str, Any], target: str = "draft") -> ValidationOut:
    from pydantic import ValidationError

    from strategy.dsl.schema import StrategyDocument
    from strategy.dsl.validate import validate_document

    try:
        doc = StrategyDocument.model_validate(dsl)
    except ValidationError as exc:
        errs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return ValidationOut(valid=False, errors=errs, warnings=[], missing_information=[])
    rep = validate_document(doc, target)  # type: ignore[arg-type]
    return ValidationOut(
        valid=not rep.errors,
        errors=list(rep.errors),
        warnings=list(rep.warnings),
        missing_information=list(rep.missing_information),
    )


def _vout(v: StrategyVersion, with_validation: bool = False) -> VersionOut:
    return VersionOut(
        id=v.id,
        strategy_id=v.strategy_id,
        version_no=v.version_no,
        parent_version_id=v.parent_version_id,
        status=v.status,
        dsl=v.dsl,
        dsl_schema_version=v.dsl_schema_version,
        dsl_hash=v.dsl_hash,
        source_text=v.source_text,
        source_language=v.source_language,
        created_by=v.created_by,
        change_summary=v.change_summary,
        created_at=v.created_at,
        frozen_at=v.frozen_at,
        validation=_validate(v.dsl) if with_validation else None,
    )


async def _latest(db: DB, strategy_id: int) -> StrategyVersion | None:
    res = await db.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_no.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def _sout(db: DB, s: Strategy) -> StrategyOut:
    lv = await _latest(db, s.id)
    return StrategyOut(
        id=s.id,
        name=s.name,
        category=s.category,
        origin=s.origin,
        description=s.description,
        tags=list(s.tags),
        is_archived=s.is_archived,
        created_at=s.created_at,
        latest_version=_vout(lv) if lv else None,
    )


async def _owned(db: DB, user: User, strategy_id: int) -> Strategy:
    s = await db.get(Strategy, strategy_id)
    if s is None or s.user_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    return s


async def _owned_version(db: DB, user: User, version_id: int) -> StrategyVersion:
    v = await db.get(StrategyVersion, version_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    await _owned(db, user, v.strategy_id)
    return v


@router.get("", response_model=list[StrategyOut])
async def list_strategies(db: DB, user: User, include_archived: bool = False) -> list[StrategyOut]:
    q = (
        select(Strategy)
        .where(Strategy.user_id == user.user_id)
        .order_by(Strategy.created_at.desc())
    )
    if not include_archived:
        q = q.where(Strategy.is_archived.is_(False))
    return [await _sout(db, s) for s in (await db.execute(q)).scalars().all()]


@router.post("", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def create_strategy(body: StrategyIn, db: DB, user: User) -> StrategyOut:
    s = Strategy(
        user_id=user.user_id,
        name=body.name,
        category=body.category,
        origin=body.origin,
        description=body.description,
        tags=body.tags,
    )
    db.add(s)
    await db.flush()
    await audit(
        db, user_id=user.user_id, action="strategy.create", entity_type="strategy", entity_id=s.id
    )
    await db.commit()
    return await _sout(db, s)


@router.get("/{strategy_id}", response_model=StrategyOut)
async def get_strategy(strategy_id: int, db: DB, user: User) -> StrategyOut:
    return await _sout(db, await _owned(db, user, strategy_id))


@router.post("/{strategy_id}/archive", response_model=StrategyOut)
async def archive_strategy(strategy_id: int, db: DB, user: User) -> StrategyOut:
    s = await _owned(db, user, strategy_id)
    s.is_archived = True
    await audit(
        db, user_id=user.user_id, action="strategy.archive", entity_type="strategy", entity_id=s.id
    )
    await db.commit()
    return await _sout(db, s)


@router.post("/validate", response_model=ValidationOut)
async def validate_dsl(body: VersionIn, _: User) -> ValidationOut:
    return _validate(body.dsl)


@router.get("/{strategy_id}/versions", response_model=list[VersionOut])
async def list_versions(strategy_id: int, db: DB, user: User) -> list[VersionOut]:
    await _owned(db, user, strategy_id)
    res = await db.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_no)
    )
    return [_vout(v) for v in res.scalars().all()]


@router.post(
    "/{strategy_id}/versions", response_model=VersionOut, status_code=status.HTTP_201_CREATED
)
async def create_version(strategy_id: int, body: VersionIn, db: DB, user: User) -> VersionOut:
    """Create a new DRAFT version. Versions are immutable once they leave draft (DB trigger)."""
    await _owned(db, user, strategy_id)
    validation = _validate(body.dsl)
    if validation.errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "strategy DSL invalid", "errors": validation.errors},
        )
    next_no = (
        await db.execute(
            select(func.coalesce(func.max(StrategyVersion.version_no), 0) + 1).where(
                StrategyVersion.strategy_id == strategy_id
            )
        )
    ).scalar_one()
    canonical = orjson.dumps(body.dsl, option=orjson.OPT_SORT_KEYS)
    v = StrategyVersion(
        strategy_id=strategy_id,
        version_no=next_no,
        parent_version_id=body.parent_version_id,
        status=StrategyVersionStatus.DRAFT,
        dsl=body.dsl,
        dsl_schema_version=str(body.dsl.get("dsl_schema_version", "1.0")),
        dsl_hash=hashlib.sha256(canonical).hexdigest(),
        source_text=body.source_text,
        source_language=body.source_language,
        created_by=CreatedBy.USER,
        change_summary=body.change_summary,
    )
    db.add(v)
    await db.flush()
    await audit(
        db,
        user_id=user.user_id,
        action="strategy.version.create",
        entity_type="strategy_version",
        entity_id=v.id,
        after={"version_no": next_no},
    )
    await db.commit()
    out = _vout(v)
    out.validation = validation
    return out


@router.get("/versions/{version_id}", response_model=VersionOut)
async def get_version(version_id: int, db: DB, user: User) -> VersionOut:
    return _vout(await _owned_version(db, user, version_id), with_validation=True)


@router.post(
    "/versions/{version_id}/edit", response_model=VersionOut, status_code=status.HTTP_201_CREATED
)
async def edit_as_new_version(version_id: int, body: VersionIn, db: DB, user: User) -> VersionOut:
    """Editing never mutates: it clones into a new draft with parent_version_id set."""
    parent = await _owned_version(db, user, version_id)
    body.parent_version_id = parent.id
    return await create_version(parent.strategy_id, body, db, user)


@router.post("/versions/{version_id}/transition", response_model=VersionOut)
async def transition_version(version_id: int, body: TransitionIn, db: DB, user: User) -> VersionOut:
    v = await _owned_version(db, user, version_id)
    if body.to_status not in TRANSITIONS[v.status]:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"cannot move from {v.status.value} to {body.to_status.value}"
        )
    if body.to_status == StrategyVersionStatus.APPROVED_LIVE and not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner can approve for live")
    frm = v.status
    v.status = body.to_status
    if frm == StrategyVersionStatus.DRAFT:
        v.frozen_at = utcnow()
    db.add(
        StrategyApproval(
            version_id=v.id,
            user_id=user.user_id,
            from_status=frm,
            to_status=body.to_status,
            evidence=body.evidence,
            decision=(
                Decision.REJECTED
                if body.to_status in (StrategyVersionStatus.REJECTED, StrategyVersionStatus.RETIRED)
                else Decision.APPROVED
            ),
            note=body.note,
        )
    )
    await audit(
        db,
        user_id=user.user_id,
        action="strategy.version.transition",
        entity_type="strategy_version",
        entity_id=v.id,
        before={"status": frm.value},
        after={"status": body.to_status.value},
        reason=body.note,
    )
    await db.commit()
    return _vout(v)
