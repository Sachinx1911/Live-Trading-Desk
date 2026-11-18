"""Persistence for market regimes (daily + intraday) and the events calendar lookup."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Event
from core.db.models import RegimeDaily as DailyRow
from core.db.models import RegimeIntraday as IntradayRow
from core.db.models._enums import (
    RegimeDayType,
    RegimeStrength,
    RegimeStructure,
    RegimeTrend,
    RegimeVolatility,
)
from core.time import IST, ensure_utc, utcnow
from strategy.regime import RegimeDaily, RegimeIntraday


def _dec(v: float | None) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def to_daily(row: DailyRow) -> RegimeDaily:
    return RegimeDaily(
        date=row.date,
        trend=row.trend.value,
        strength=row.strength.value,
        volatility=row.volatility.value,
        structure=row.structure.value,
        adx=None if row.adx is None else float(row.adx),
        ema20=None if row.ema20 is None else float(row.ema20),
        ema50=None if row.ema50 is None else float(row.ema50),
        ema200=None if row.ema200 is None else float(row.ema200),
        atr_pct=None if row.atr_pct is None else float(row.atr_pct),
        vix=None if row.vix is None else float(row.vix),
        vix_percentile=None if row.vix_percentile is None else float(row.vix_percentile),
        event_day=row.event_day,
        events=[str(e) for e in (row.events or [])],
        computed_at=row.computed_at,
    )


def to_intraday(row: IntradayRow) -> RegimeIntraday:
    return RegimeIntraday(
        ts=row.ts,
        day_type=row.day_type.value,
        or_high=None if row.or_high is None else float(row.or_high),
        or_low=None if row.or_low is None else float(row.or_low),
        vwap_distance_pct=None if row.vwap_distance_pct is None else float(row.vwap_distance_pct),
        atr_ratio=None if row.atr_ratio is None else float(row.atr_ratio),
    )


async def upsert_daily(session: AsyncSession, instrument_id: int, r: RegimeDaily) -> None:
    values = {
        "instrument_id": instrument_id,
        "date": r.date,
        "trend": RegimeTrend(r.trend),
        "strength": RegimeStrength(r.strength),
        "volatility": RegimeVolatility(r.volatility),
        "structure": RegimeStructure(r.structure),
        "adx": _dec(r.adx),
        "ema20": _dec(r.ema20),
        "ema50": _dec(r.ema50),
        "ema200": _dec(r.ema200),
        "atr_pct": _dec(r.atr_pct),
        "vix": _dec(r.vix),
        "vix_percentile": _dec(r.vix_percentile),
        "event_day": r.event_day,
        "events": list(r.events),
        "computed_at": r.computed_at or utcnow(),
    }
    stmt = insert(DailyRow).values(**values)
    update = {k: v for k, v in values.items() if k not in ("instrument_id", "date")}
    stmt = stmt.on_conflict_do_update(index_elements=["instrument_id", "date"], set_=update)
    await session.execute(stmt)


async def upsert_intraday(session: AsyncSession, instrument_id: int, r: RegimeIntraday) -> None:
    values = {
        "instrument_id": instrument_id,
        "ts": ensure_utc(r.ts),
        "day_type": RegimeDayType(r.day_type),
        "or_high": _dec(r.or_high),
        "or_low": _dec(r.or_low),
        "vwap_distance_pct": _dec(r.vwap_distance_pct),
        "atr_ratio": _dec(r.atr_ratio),
    }
    stmt = insert(IntradayRow).values(**values)
    update = {k: v for k, v in values.items() if k not in ("instrument_id", "ts")}
    stmt = stmt.on_conflict_do_update(index_elements=["instrument_id", "ts"], set_=update)
    await session.execute(stmt)


async def fetch_daily(
    session: AsyncSession, instrument_id: int, start: date, end: date
) -> list[RegimeDaily]:
    q = (
        select(DailyRow)
        .where(
            DailyRow.instrument_id == instrument_id, DailyRow.date >= start, DailyRow.date <= end
        )
        .order_by(DailyRow.date)
    )
    return [to_daily(r) for r in (await session.execute(q)).scalars().all()]


async def latest_daily(session: AsyncSession, instrument_id: int) -> RegimeDaily | None:
    q = (
        select(DailyRow)
        .where(DailyRow.instrument_id == instrument_id)
        .order_by(DailyRow.date.desc())
        .limit(1)
    )
    row = (await session.execute(q)).scalar_one_or_none()
    return None if row is None else to_daily(row)


async def latest_intraday(
    session: AsyncSession, instrument_id: int, day: date | None = None
) -> RegimeIntraday | None:
    q = select(IntradayRow).where(IntradayRow.instrument_id == instrument_id)
    if day is not None:
        start = datetime.combine(day, datetime.min.time(), tzinfo=IST)
        q = q.where(IntradayRow.ts >= start, IntradayRow.ts < start + timedelta(days=1))
    row = (await session.execute(q.order_by(IntradayRow.ts.desc()).limit(1))).scalar_one_or_none()
    return None if row is None else to_intraday(row)


async def events_for_day(session: AsyncSession, day: date) -> list[str]:
    """Titles of calendar events starting on that IST day (RBI, Fed, budget, expiry ...)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=IST)
    q = (
        select(Event)
        .where(Event.starts_at >= start, Event.starts_at < start + timedelta(days=1))
        .order_by(Event.starts_at)
    )
    return [f"{e.event_type.value}: {e.title}" for e in (await session.execute(q)).scalars().all()]
