"""JARVIS accuracy loop (Mark 1 Stage 4.6): recorded views, hit-rates and AI spend.

Views are recorded by the tool server's `record_view` tool (jarvis) or, for manual and test
entry, by the owner through POST /ai/observations, which calls the same service. Reference
prices are always taken by the service, never accepted from the caller. Scoring runs in the
worker. Nothing here is read by any strategy, risk check or order path (ADR-009).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, CurrentUser, State, User
from core.db.models import AiViewScore
from core.time import utcnow
from market_data.views.report import Group, ViewRow, aggregate, ai_spend_by_day, list_views
from market_data.views.scoring import CONFIDENCE_BANDS, HORIZON_BUCKETS
from market_data.views.service import RecordViewIn, RecordViewOut, ViewRefused, record_view

router = APIRouter(prefix="/ai", tags=["ai"])

StatusQ = Literal["pending", "hit", "miss", "void"]
DirectionQ = Literal["up", "down", "sideways"]


class ObservationOut(BaseModel):
    id: int
    ts: datetime
    caller: str
    mode: str | None
    instrument_id: int
    symbol: str
    direction: str
    horizon_days: int
    confidence: float
    invalidation: str | None
    invalidation_price: float | None
    statement: str | None
    ref_price: float
    ref_source: str
    ref_freshness: str
    ref_ts: datetime
    tool_call_id: int | None
    due_date: date
    status: StatusQ
    close_price: float | None
    return_pct: float | None
    threshold_pct: float | None
    scored_at: datetime | None
    void_reason: str | None


class ObservationListOut(BaseModel):
    count: int
    items: list[ObservationOut]


class GroupOut(BaseModel):
    key: str
    total: int
    pending: int
    hits: int
    misses: int
    voids: int
    hit_rate: float | None  # hits / (hits + misses); None when nothing is graded
    mean_confidence: float | None


class BandOut(BaseModel):
    key: str
    low: float
    high: float


class SpendDayOut(BaseModel):
    day: date
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    calls_without_cost: int


class SpendOut(BaseModel):
    days: int
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float | None
    calls_without_cost: int
    daily_token_budget: int
    by_day: list[SpendDayOut]


class AccuracyOut(BaseModel):
    threshold_pct: float  # the current setting, used for new grades
    thresholds_in_use: list[float]  # thresholds stored on existing grades (rebuild to unify)
    grace_days: int
    provider: str  # closes come from this provider's daily candles
    overall: GroupOut
    by_instrument: list[GroupOut]
    by_horizon: list[GroupOut]
    by_mode: list[GroupOut]
    by_caller: list[GroupOut]
    by_confidence: list[GroupOut]
    by_direction: list[GroupOut]
    confidence_bands: list[BandOut]
    horizon_buckets: list[str]
    recent: list[ObservationOut]
    spend: SpendOut


def _f(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def _obs(r: ViewRow) -> ObservationOut:
    return ObservationOut(
        id=r.id,
        ts=r.ts,
        caller=r.caller,
        mode=r.mode,
        instrument_id=r.instrument_id,
        symbol=r.symbol,
        direction=r.direction,
        horizon_days=r.horizon_days,
        confidence=float(r.confidence),
        invalidation=r.invalidation,
        invalidation_price=_f(r.invalidation_price),
        statement=r.statement,
        ref_price=float(r.ref_price),
        ref_source=r.ref_source,
        ref_freshness=r.ref_freshness,
        ref_ts=r.ref_ts,
        tool_call_id=r.tool_call_id,
        due_date=r.due_date,
        status=r.status,
        close_price=_f(r.close_price),
        return_pct=_f(r.return_pct),
        threshold_pct=_f(r.threshold_pct),
        scored_at=r.scored_at,
        void_reason=r.void_reason,
    )


def _g(g: Group) -> GroupOut:
    return GroupOut(**g.__dict__)


def _require_owner(user: CurrentUser) -> None:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")


@router.get("/observations", response_model=ObservationListOut)
async def observations(
    db: DB,
    _: User,
    symbol: str | None = Query(None, max_length=40),
    caller: str | None = Query(None, max_length=40),
    mode: str | None = Query(None, max_length=20),
    direction: DirectionQ | None = None,
    status_: Annotated[StatusQ | None, Query(alias="status")] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> ObservationListOut:
    rows = await list_views(
        db,
        symbol=symbol,
        caller=caller,
        mode=mode,
        direction=direction,
        status=status_,
        since=from_,
        until=to,
        limit=limit,
        offset=offset,
    )
    return ObservationListOut(count=len(rows), items=[_obs(r) for r in rows])


@router.get("/accuracy", response_model=AccuracyOut)
async def accuracy(
    db: DB,
    state: State,
    _: User,
    caller: str | None = Query(None, max_length=40),
    mode: str | None = Query(None, max_length=20),
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    spend_days: int = Query(30, ge=1, le=365),
    recent: int = Query(50, ge=0, le=500),
) -> AccuracyOut:
    s = state.settings
    rows = await list_views(db, caller=caller, mode=mode, since=from_, until=to)
    acc = aggregate(rows)
    used = (await db.execute(select(AiViewScore.threshold_pct).distinct())).scalars().all()
    spend = await ai_spend_by_day(db, days=spend_days, now=utcnow())
    costs = [d.cost_usd for d in spend if d.cost_usd is not None]
    return AccuracyOut(
        threshold_pct=s.view_score_threshold_pct,
        thresholds_in_use=sorted(float(t) for t in used),
        grace_days=s.view_score_grace_days,
        provider=s.default_market_data_provider,
        overall=_g(acc.overall),
        by_instrument=[_g(g) for g in acc.by_instrument],
        by_horizon=[_g(g) for g in acc.by_horizon],
        by_mode=[_g(g) for g in acc.by_mode],
        by_caller=[_g(g) for g in acc.by_caller],
        by_confidence=[_g(g) for g in acc.by_confidence],
        by_direction=[_g(g) for g in acc.by_direction],
        confidence_bands=[
            BandOut(key=k, low=float(lo), high=float(hi)) for k, lo, hi in CONFIDENCE_BANDS
        ],
        horizon_buckets=[b[0] for b in HORIZON_BUCKETS],
        recent=[_obs(r) for r in rows[:recent]],
        spend=SpendOut(
            days=spend_days,
            total_calls=sum(d.calls for d in spend),
            total_input_tokens=sum(d.input_tokens for d in spend),
            total_output_tokens=sum(d.output_tokens for d in spend),
            total_cost_usd=float(sum(costs)) if costs else None,
            calls_without_cost=sum(d.calls_without_cost for d in spend),
            daily_token_budget=s.ai_daily_token_budget,
            by_day=[
                SpendDayOut(
                    day=d.day,
                    calls=d.calls,
                    input_tokens=d.input_tokens,
                    output_tokens=d.output_tokens,
                    cost_usd=_f(d.cost_usd),
                    calls_without_cost=d.calls_without_cost,
                )
                for d in spend
            ],
        ),
    )


@router.post("/observations", response_model=RecordViewOut, status_code=status.HTTP_201_CREATED)
async def create_observation(db: DB, state: State, user: User, body: RecordViewIn) -> RecordViewOut:
    """Owner-only manual / test entry through the same service the tool server uses."""
    _require_owner(user)
    try:
        out = await record_view(db, state.redis, state.settings, body, commit=False)
    except ViewRefused as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, {"code": e.code, "message": str(e)}
        ) from e
    await audit(
        db,
        user_id=user.user_id,
        action="ai.observation.create",
        entity_type="ai_observation",
        entity_id=out.observation_id,
        after=out.model_dump(mode="json"),
    )
    await db.commit()
    return out


@router.post("/views/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild(db: DB, state: State, user: User) -> dict[str, str]:
    _require_owner(user)
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job("rebuild_ai_view_scores")
    finally:
        await pool.aclose()
    await audit(
        db, user_id=user.user_id, action="ai.views.rebuild.enqueue", entity_type="ai_view_scores"
    )
    await db.commit()
    return {"status": "queued"}
