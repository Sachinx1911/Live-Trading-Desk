"""Historical candle backfill from a provider into historical_candles, chunked and idempotent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.models import Timeframe
from core.time import ensure_utc
from market_data.repo.candles import upsert_candles
from providers.base import MarketDataProvider

log = get_logger(__name__)

DEFAULT_MAX_DAYS: dict[Timeframe, int] = {
    Timeframe.D1: 365,
    Timeframe.W1: 365 * 5,
    Timeframe.MN1: 365 * 10,
}
DEFAULT_INTRADAY_MAX_DAYS = 30


@dataclass(frozen=True)
class BackfillResult:
    instrument_id: int
    timeframe: Timeframe
    provider: str
    requested_from: datetime
    requested_to: datetime
    chunks: int
    rows: int
    first_ts: datetime | None
    last_ts: datetime | None


def _max_days(provider: MarketDataProvider, tf: Timeframe) -> int:
    limits: dict[Timeframe, int] = getattr(provider, "historical_limits", {}) or {}
    if tf in limits:
        return int(limits[tf])
    return DEFAULT_MAX_DAYS.get(tf, DEFAULT_INTRADAY_MAX_DAYS)


async def backfill_candles(
    provider: MarketDataProvider,
    session: AsyncSession,
    instrument_id: int,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    *,
    db_instrument_id: int | None = None,
) -> BackfillResult:
    """Fetch [start, end) in provider-sized chunks and upsert. `db_instrument_id` lets a
    provider-provisional id be stored under the canonical database id."""
    start, end = ensure_utc(start), ensure_utc(end)
    step = timedelta(days=_max_days(provider, timeframe))
    chunks = rows = 0
    first: datetime | None = None
    last: datetime | None = None
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        candles = await provider.get_candles(instrument_id, timeframe, cur, nxt)
        if db_instrument_id is not None and db_instrument_id != instrument_id:
            candles = [c.model_copy(update={"instrument_id": db_instrument_id}) for c in candles]
        if candles:
            rows += await upsert_candles(session, candles)
            lo, hi = min(c.ts for c in candles), max(c.ts for c in candles)
            first = lo if first is None or lo < first else first
            last = hi if last is None or hi > last else last
        chunks += 1
        cur = nxt
    log.info(
        "candles.backfilled",
        provider=provider.info.code,
        instrument_id=db_instrument_id or instrument_id,
        timeframe=timeframe.value,
        chunks=chunks,
        rows=rows,
    )
    return BackfillResult(
        instrument_id=db_instrument_id or instrument_id,
        timeframe=timeframe,
        provider=provider.info.code,
        requested_from=start,
        requested_to=end,
        chunks=chunks,
        rows=rows,
        first_ts=first,
        last_ts=last,
    )
