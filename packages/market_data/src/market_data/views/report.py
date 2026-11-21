"""Read side of the accuracy loop: observation lists, hit-rates and AI spend.

Hit-rate = hits / (hits + misses). Pending and void views are counted but never enter a
hit-rate. The pure `aggregate` does the grouping so it is tested without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.calendar import nse_calendar
from core.db.models import AiCall, AiObservation, AiViewScore
from core.db.models import Instrument as InstrumentRow
from core.time import ensure_utc
from market_data.views.scoring import (
    CONFIDENCE_BANDS,
    HORIZON_BUCKETS,
    confidence_band,
    due_date,
    horizon_bucket,
)

Status = Literal["pending", "hit", "miss", "void"]


@dataclass(frozen=True)
class ViewRow:
    id: int
    ts: datetime
    caller: str
    mode: str | None
    instrument_id: int
    symbol: str
    direction: str
    horizon_days: int
    confidence: Decimal
    invalidation: str | None
    invalidation_price: Decimal | None
    statement: str | None
    ref_price: Decimal
    ref_source: str
    ref_freshness: str
    ref_ts: datetime
    tool_call_id: int | None
    due_date: date
    status: Status
    close_price: Decimal | None
    return_pct: Decimal | None
    threshold_pct: Decimal | None
    scored_at: datetime | None
    void_reason: str | None


@dataclass(frozen=True)
class Group:
    key: str
    total: int
    pending: int
    hits: int
    misses: int
    voids: int
    hit_rate: float | None
    mean_confidence: float | None  # of graded (hit/miss) views; the calibration "promise"


def _group(key: str, rows: list[ViewRow]) -> Group:
    hits = sum(r.status == "hit" for r in rows)
    misses = sum(r.status == "miss" for r in rows)
    graded = [r for r in rows if r.status in ("hit", "miss")]
    return Group(
        key=key,
        total=len(rows),
        pending=sum(r.status == "pending" for r in rows),
        hits=hits,
        misses=misses,
        voids=sum(r.status == "void" for r in rows),
        hit_rate=hits / (hits + misses) if hits + misses else None,
        mean_confidence=(
            float(sum(r.confidence for r in graded) / len(graded)) if graded else None
        ),
    )


def group_by(
    rows: Iterable[ViewRow], key: Callable[[ViewRow], str], order: Iterable[str] | None = None
) -> list[Group]:
    buckets: dict[str, list[ViewRow]] = {}
    for k in order or ():
        buckets[k] = []
    for r in rows:
        buckets.setdefault(key(r), []).append(r)
    keys = list(buckets) if order is not None else sorted(buckets)
    return [_group(k, buckets[k]) for k in keys]


@dataclass(frozen=True)
class Accuracy:
    overall: Group
    by_instrument: list[Group]
    by_horizon: list[Group]
    by_mode: list[Group]
    by_caller: list[Group]
    by_confidence: list[Group]
    by_direction: list[Group]


def aggregate(rows: list[ViewRow]) -> Accuracy:
    return Accuracy(
        overall=_group("all", rows),
        by_instrument=group_by(rows, lambda r: r.symbol),
        by_horizon=group_by(
            rows, lambda r: horizon_bucket(r.horizon_days), [b[0] for b in HORIZON_BUCKETS]
        ),
        by_mode=group_by(rows, lambda r: r.mode or "(none)"),
        by_caller=group_by(rows, lambda r: r.caller),
        by_confidence=group_by(
            rows, lambda r: confidence_band(r.confidence), [b[0] for b in CONFIDENCE_BANDS]
        ),
        by_direction=group_by(rows, lambda r: r.direction, ["up", "down", "sideways"]),
    )


async def list_views(
    db: AsyncSession,
    *,
    symbol: str | None = None,
    caller: str | None = None,
    mode: str | None = None,
    direction: str | None = None,
    status: Status | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[ViewRow]:
    """Newest first. `status` filters after the join (pending = no score row yet)."""
    q = (
        select(AiObservation, InstrumentRow.symbol, AiViewScore)
        .join(InstrumentRow, InstrumentRow.id == AiObservation.instrument_id)
        .outerjoin(AiViewScore, AiViewScore.observation_id == AiObservation.id)
        .order_by(AiObservation.ts.desc(), AiObservation.id.desc())
    )
    if symbol:
        q = q.where(InstrumentRow.symbol == symbol.upper())
    if caller:
        q = q.where(AiObservation.caller == caller)
    if mode:
        q = q.where(AiObservation.mode == mode)
    if direction:
        q = q.where(AiObservation.direction == direction)
    if since:
        q = q.where(AiObservation.ts >= ensure_utc(since))
    if until:
        q = q.where(AiObservation.ts < ensure_utc(until))
    if status == "pending":
        q = q.where(AiViewScore.id.is_(None))
    elif status is not None:
        q = q.where(AiViewScore.outcome == status)
    if limit is not None:
        q = q.limit(limit).offset(offset)
    cal = nse_calendar()
    out: list[ViewRow] = []
    for o, sym, s in (await db.execute(q)).all():
        out.append(
            ViewRow(
                id=o.id,
                ts=ensure_utc(o.ts),
                caller=o.caller,
                mode=o.mode,
                instrument_id=o.instrument_id,
                symbol=sym,
                direction=o.direction,
                horizon_days=o.horizon_days,
                confidence=Decimal(o.confidence),
                invalidation=o.invalidation,
                invalidation_price=o.invalidation_price,
                statement=o.statement,
                ref_price=Decimal(o.ref_price),
                ref_source=o.ref_source,
                ref_freshness=o.ref_freshness,
                ref_ts=ensure_utc(o.ref_ts),
                tool_call_id=o.tool_call_id,
                due_date=s.due_date if s else due_date(cal, o.ts, o.horizon_days),
                status=_status(s.outcome) if s else "pending",
                close_price=s.close_price if s else None,
                return_pct=s.return_pct if s else None,
                threshold_pct=s.threshold_pct if s else None,
                scored_at=ensure_utc(s.scored_at) if s else None,
                void_reason=(s.detail or {}).get("reason") if s else None,
            )
        )
    return out


def _status(v: str) -> Status:
    if v == "hit":
        return "hit"
    if v == "miss":
        return "miss"
    return "void"


@dataclass(frozen=True)
class SpendDay:
    day: date
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None  # None when no call that day carried a cost
    calls_without_cost: int


async def ai_spend_by_day(db: AsyncSession, *, days: int, now: datetime) -> list[SpendDay]:
    """`ai_calls` per IST day for the last `days` days (only days with calls)."""
    local_day = cast(func.timezone("Asia/Kolkata", AiCall.ts), Date)
    since = ensure_utc(now) - timedelta(days=days)
    q = (
        select(
            local_day,
            func.count(AiCall.id),
            func.coalesce(func.sum(AiCall.input_tokens), 0),
            func.coalesce(func.sum(AiCall.output_tokens), 0),
            func.sum(AiCall.cost_usd),
            func.count(AiCall.id).filter(AiCall.cost_usd.is_(None)),
        )
        .where(AiCall.ts >= since)
        .group_by(local_day)
        .order_by(local_day.desc())
    )
    return [
        SpendDay(d, int(n), int(i), int(o), Decimal(c) if c is not None else None, int(nc))
        for d, n, i, o, c, nc in (await db.execute(q)).all()
    ]
