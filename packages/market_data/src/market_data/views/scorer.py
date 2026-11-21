"""Score matured observations into `ai_view_scores` (derived, rebuildable).

The close at the due date is the stored daily (1d) candle of ONE provider (the active
provider, as for breadth and the scanner), never a mix. An observation is:

- pending (no row) until its due date's session has closed and, if the close is missing,
  until `grace_days` more trading days have closed;
- hit / miss once the due-date close is stored (`scoring.grade`);
- void when the close is still missing after the grace period, or the reference price is not
  positive. A later rebuild re-grades voids whose close has arrived since.

Idempotent: a normal run only adds rows for observations without one (insert ... on conflict
do nothing), so re-running it changes nothing. `rebuild=True` deletes every score and grades
all observations again from observations + candles with the current threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.calendar import ExchangeCalendar, nse_calendar
from core.db.models import AiObservation, AiViewScore, DataProvider, HistoricalCandle
from core.models import Timeframe
from core.time import ensure_utc
from market_data.views.scoring import (
    Direction,
    anchor_date,
    due_date,
    grade,
    is_matured,
    past_grace,
)

RETURN_Q = Decimal("0.0001")


@dataclass
class ScoreRun:
    considered: int = 0
    pending: int = 0
    stored: dict[str, int] = field(default_factory=lambda: {"hit": 0, "miss": 0, "void": 0})
    rebuilt: bool = False
    deleted: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "considered": self.considered,
            "pending": self.pending,
            "stored": dict(self.stored),
            "rebuilt": self.rebuilt,
            "deleted": self.deleted,
        }


async def daily_close(
    db: AsyncSession, cal: ExchangeCalendar, instrument_id: int, provider: str, day: date
) -> Decimal | None:
    """Close of the stored 1d candle of `provider` whose exchange-local date is `day`."""
    start = ensure_utc(datetime.combine(day, datetime.min.time(), tzinfo=cal.tz))
    q = (
        select(HistoricalCandle.close)
        .join(DataProvider, DataProvider.id == HistoricalCandle.provider_id)
        .where(
            HistoricalCandle.instrument_id == instrument_id,
            HistoricalCandle.timeframe == Timeframe.D1,
            DataProvider.code == provider,
            HistoricalCandle.ts >= start,
            HistoricalCandle.ts < start + timedelta(days=1),
        )
        .order_by(HistoricalCandle.ts.desc())
        .limit(1)
    )
    v = (await db.execute(q)).scalar_one_or_none()
    return Decimal(v) if v is not None else None


async def score_views(
    db: AsyncSession,
    *,
    provider: str,
    threshold_pct: Decimal,
    grace_days: int,
    now: datetime,
    rebuild: bool = False,
    cal: ExchangeCalendar | None = None,
) -> ScoreRun:
    """Grade every matured, unscored observation. The caller commits."""
    cal = cal or nse_calendar()
    now = ensure_utc(now)
    run = ScoreRun(rebuilt=rebuild)
    if rebuild:
        res = await db.execute(delete(AiViewScore))
        run.deleted = int(getattr(res, "rowcount", 0) or 0)
    q = (
        select(AiObservation)
        .outerjoin(AiViewScore, AiViewScore.observation_id == AiObservation.id)
        .where(AiViewScore.id.is_(None))
        .order_by(AiObservation.id)
    )
    for obs in (await db.execute(q)).scalars():
        run.considered += 1
        due = due_date(cal, obs.ts, obs.horizon_days)
        if not is_matured(cal, due, now):
            run.pending += 1
            continue
        detail: dict[str, Any] = {
            "provider": provider,
            "anchor_date": anchor_date(cal, obs.ts).isoformat(),
            "close_source": f"{provider}:candle_1d",
            "ref_source": obs.ref_source,
            "ref_freshness": obs.ref_freshness,
        }
        close = await daily_close(db, cal, obs.instrument_id, provider, due)
        ref = Decimal(obs.ref_price)
        if close is not None and ref > 0:
            g = grade(_direction(obs.direction), ref, close, threshold_pct)
            outcome, ret = g.outcome, g.return_pct
        elif close is not None:
            outcome, ret = "void", None
            detail["reason"] = "reference price is not positive"
        elif past_grace(cal, due, now, grace_days):
            outcome, ret = "void", None
            detail["reason"] = f"no daily close for {due.isoformat()} after {grace_days} days"
        else:
            run.pending += 1
            continue
        stmt = (
            insert(AiViewScore)
            .values(
                observation_id=obs.id,
                due_date=due,
                close_price=close,
                return_pct=ret.quantize(RETURN_Q) if ret is not None else None,
                threshold_pct=threshold_pct,
                outcome=outcome,
                detail=detail,
                scored_at=now,
            )
            .on_conflict_do_nothing(index_elements=["observation_id"])
        )
        await db.execute(stmt)
        run.stored[outcome] += 1
    await db.flush()
    return run


def _direction(v: str) -> Direction:
    if v == "up":
        return "up"
    if v == "down":
        return "down"
    if v == "sideways":
        return "sideways"
    raise ValueError(f"unknown direction {v!r}")
