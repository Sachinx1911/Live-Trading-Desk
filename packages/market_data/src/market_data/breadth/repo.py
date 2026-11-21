"""Load daily closes for breadth and persist / read `market_breadth` rows."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

import polars as pl
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Exchange, HistoricalCandle, MarketBreadth
from core.db.models import Instrument as InstrumentRow
from core.db.models._enums import InstrumentType
from core.models import Timeframe
from core.time import IST, ensure_utc, utcnow
from market_data.breadth.compute import BreadthRow, bars_frame
from market_data.repo._lookup import provider_id

# EMA 200 is SMA-seeded; ~3 years of warm-up makes the seed's weight negligible (<1 %).
WARMUP_DAYS = 1100


def _ist_midnight_utc(d: date) -> datetime:
    return ensure_utc(datetime.combine(d, datetime.min.time(), tzinfo=IST))


async def load_closes(
    session: AsyncSession,
    *,
    provider: str,
    symbols: Sequence[str],
    start: date,
    end: date,
    instrument_types: Sequence[InstrumentType] = (InstrumentType.EQUITY,),
    exchange: str = "NSE",
) -> pl.DataFrame:
    """Daily closes (symbol, IST day, close) of one provider for `start..end` inclusive.
    Never mixes providers (same rule as backtests and the scanner)."""
    pid = await provider_id(session, provider)
    q = (
        select(InstrumentRow.symbol, HistoricalCandle.ts, HistoricalCandle.close)
        .join(InstrumentRow, InstrumentRow.id == HistoricalCandle.instrument_id)
        .join(Exchange, Exchange.id == InstrumentRow.exchange_id)
        .where(
            Exchange.code == exchange,
            InstrumentRow.symbol.in_(list(symbols)),
            InstrumentRow.instrument_type.in_(list(instrument_types)),
            HistoricalCandle.provider_id == pid,
            HistoricalCandle.timeframe == Timeframe.D1,
            HistoricalCandle.ts >= _ist_midnight_utc(start),
            HistoricalCandle.ts < _ist_midnight_utc(end + timedelta(days=1)),
        )
        .order_by(InstrumentRow.symbol, HistoricalCandle.ts)
    )
    rows = (await session.execute(q)).all()
    return bars_frame((s, ensure_utc(ts).astimezone(IST).date(), float(c)) for s, ts, c in rows)


def _dec(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


async def upsert_rows(
    session: AsyncSession, *, provider: str, universe: str, rows: Sequence[BreadthRow]
) -> int:
    if not rows:
        return 0
    pid = await provider_id(session, provider)
    now = utcnow()
    for r in rows:
        values = {
            "universe_size": r.universe_size,
            "advances": r.advances,
            "declines": r.declines,
            "unchanged": r.unchanged,
            "new_52w_high": r.new_52w_high,
            "new_52w_low": r.new_52w_low,
            "above_ema50_pct": _dec(r.above_ema50_pct),
            "above_ema200_pct": _dec(r.above_ema200_pct),
            "index_moves": r.index_moves,
            "computed_at": now,
        }
        stmt = (
            insert(MarketBreadth)
            .values(as_of_date=r.as_of_date, universe=universe, provider_id=pid, **values)
            .on_conflict_do_update(
                index_elements=["as_of_date", "universe", "provider_id"], set_=values
            )
        )
        await session.execute(stmt)
    await session.flush()
    return len(rows)


async def list_breadth(
    session: AsyncSession,
    *,
    provider: str,
    universe: str,
    start: date | None = None,
    end: date | None = None,
    limit: int = 400,
) -> list[MarketBreadth]:
    """Ascending by date (latest `limit` rows inside the range)."""
    pid = await provider_id(session, provider)
    q = select(MarketBreadth).where(
        MarketBreadth.provider_id == pid, MarketBreadth.universe == universe
    )
    if start:
        q = q.where(MarketBreadth.as_of_date >= start)
    if end:
        q = q.where(MarketBreadth.as_of_date <= end)
    q = q.order_by(MarketBreadth.as_of_date.desc()).limit(limit)
    return list(reversed(list((await session.execute(q)).scalars())))


async def latest_breadth(
    session: AsyncSession, *, provider: str, universe: str
) -> MarketBreadth | None:
    rows = await list_breadth(session, provider=provider, universe=universe, limit=1)
    return rows[0] if rows else None


async def count_rows(session: AsyncSession, *, provider: str, universe: str) -> int:
    pid = await provider_id(session, provider)
    q = select(func.count()).where(
        MarketBreadth.provider_id == pid, MarketBreadth.universe == universe
    )
    return int((await session.execute(q)).scalar_one())
