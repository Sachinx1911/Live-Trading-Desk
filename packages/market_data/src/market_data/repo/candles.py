"""historical_candles access: idempotent upserts, range reads, coverage."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import DataProvider, HistoricalCandle
from core.models import Candle, Timeframe
from core.time import ensure_utc, utcnow
from market_data.repo._lookup import provider_code, provider_id


@dataclass(frozen=True)
class CoverageRow:
    instrument_id: int
    timeframe: Timeframe
    provider_code: str
    first_ts: datetime
    last_ts: datetime
    count: int


async def upsert_candles(session: AsyncSession, candles: Sequence[Candle]) -> int:
    """Insert or update rows keyed by (instrument, timeframe, ts, provider). Returns rows sent."""
    if not candles:
        return 0
    rows = []
    for c in candles:
        rows.append(
            {
                "instrument_id": c.instrument_id,
                "timeframe": c.timeframe,
                "ts": c.ts,
                "provider_id": await provider_id(session, c.provider_id),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "oi": c.oi,
                "provider_ts": c.provider_ts,
            }
        )
    # asyncpg caps a statement at 32767 bind parameters (11 per row): chunk the insert.
    chunk = 2000
    for i in range(0, len(rows), chunk):
        stmt = insert(HistoricalCandle).values(rows[i : i + chunk])
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timeframe", "ts", "provider_id"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "oi": stmt.excluded.oi,
                "provider_ts": stmt.excluded.provider_ts,
                "ingested_at": func.now(),
            },
        )
        await session.execute(stmt)
    return len(rows)


async def fetch_candles(
    session: AsyncSession,
    instrument_id: int,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    provider: str | None = None,
) -> list[Candle]:
    q = (
        select(HistoricalCandle, DataProvider.code, DataProvider.is_demo)
        .join(DataProvider, DataProvider.id == HistoricalCandle.provider_id)
        .where(
            HistoricalCandle.instrument_id == instrument_id,
            HistoricalCandle.timeframe == timeframe,
            HistoricalCandle.ts >= ensure_utc(start),
            HistoricalCandle.ts < ensure_utc(end),
        )
        .order_by(HistoricalCandle.ts)
    )
    if provider is not None:
        q = q.where(DataProvider.code == provider)
    out: list[Candle] = []
    for row, code, is_demo in (await session.execute(q)).all():
        out.append(
            Candle(
                instrument_id=row.instrument_id,
                timeframe=row.timeframe,
                ts=row.ts,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                oi=row.oi,
                provider_id=code,
                provider_ts=row.provider_ts,
                received_at=row.ingested_at or utcnow(),
                is_demo=is_demo,
            )
        )
    return out


async def latest_ts(
    session: AsyncSession, instrument_id: int, timeframe: Timeframe, provider: str
) -> datetime | None:
    pid = await provider_id(session, provider)
    q = select(func.max(HistoricalCandle.ts)).where(
        HistoricalCandle.instrument_id == instrument_id,
        HistoricalCandle.timeframe == timeframe,
        HistoricalCandle.provider_id == pid,
    )
    ts = (await session.execute(q)).scalar_one_or_none()
    return ensure_utc(ts) if ts else None


async def coverage(session: AsyncSession, instrument_id: int | None = None) -> list[CoverageRow]:
    q = select(
        HistoricalCandle.instrument_id,
        HistoricalCandle.timeframe,
        HistoricalCandle.provider_id,
        func.min(HistoricalCandle.ts),
        func.max(HistoricalCandle.ts),
        func.count(),
    ).group_by(
        HistoricalCandle.instrument_id, HistoricalCandle.timeframe, HistoricalCandle.provider_id
    )
    if instrument_id is not None:
        q = q.where(HistoricalCandle.instrument_id == instrument_id)
    out: list[CoverageRow] = []
    for iid, tf, pid, first, last, n in (await session.execute(q)).all():
        out.append(
            CoverageRow(
                instrument_id=iid,
                timeframe=Timeframe(tf),
                provider_code=await provider_code(session, pid),
                first_ts=ensure_utc(first),
                last_ts=ensure_utc(last),
                count=int(n),
            )
        )
    return sorted(out, key=lambda r: (r.instrument_id, r.timeframe.value, r.provider_code))
