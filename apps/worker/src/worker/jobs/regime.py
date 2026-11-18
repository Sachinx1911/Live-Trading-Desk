"""Market regime jobs (Module 6): daily regime per tracked instrument and the intraday day
type every 15 minutes. Deterministic; idempotent (upserts keyed by instrument+date/ts)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import get_logger
from core.models import Candle, Segment, Timeframe
from core.settings import get_settings
from core.time import IST, ensure_utc, utcnow
from market_data.repo.candles import fetch_candles
from market_data.repo.instruments import get_by_symbol
from market_data.repo.regime import (
    events_for_day,
    latest_daily,
    upsert_daily,
    upsert_intraday,
)
from strategy.regime import RegimeDetector

log = get_logger(__name__)

DAILY_LOOKBACK_DAYS = 400
VIX_SYMBOL = "INDIAVIX"


def _symbols(raw: str | list[str] | None) -> list[str]:
    src = raw or get_settings().collect_symbols
    parts = src.split(",") if isinstance(src, str) else src
    return [s.strip().upper() for s in parts if s.strip()]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=IST)
    return ensure_utc(start), ensure_utc(start + timedelta(days=1))


async def _daily_series(db: Any, instrument_id: int, end_day: date) -> list[Candle]:
    provider = get_settings().default_market_data_provider
    _, end = _day_bounds(end_day)
    start = end - timedelta(days=DAILY_LOOKBACK_DAYS)
    rows = await fetch_candles(db, instrument_id, Timeframe.D1, start, end, provider)
    if not rows:  # fall back to any provider's daily rows
        rows = await fetch_candles(db, instrument_id, Timeframe.D1, start, end, None)
    return rows


async def compute_regime_daily(
    ctx: dict[str, Any], day: str | None = None, symbols: str | list[str] | None = None
) -> dict[str, Any]:
    """Daily regime for the session `day` (default: the latest completed trading day)."""
    cal = nse_calendar()
    today = utcnow().astimezone(IST).date()
    if day:
        target = date.fromisoformat(day)
    else:
        target = today if cal.is_trading_day(today) else cal.previous_trading_day(today)
    det = RegimeDetector()
    out: dict[str, Any] = {}
    async with get_session_factory()() as db:
        vix_ins = await get_by_symbol(db, "NSE", VIX_SYMBOL)
        vix_series = await _daily_series(db, vix_ins.instrument_id, target) if vix_ins else []
        events = await events_for_day(db, target)
        for sym in _symbols(symbols):
            ins = await get_by_symbol(db, "NSE", sym)
            if ins is None or ins.segment == Segment.OPTIONS:
                continue
            series = await _daily_series(db, ins.instrument_id, target)
            series = [c for c in series if ensure_utc(c.ts).astimezone(IST).date() <= target]
            if len(series) < 30:
                out[sym] = "insufficient daily history"
                continue
            vix_for = [] if sym == VIX_SYMBOL else vix_series
            r = det.daily(series, vix_for, events, computed_at=utcnow())
            await upsert_daily(db, ins.instrument_id, r)
            out[sym] = f"{r.date} {r.trend}/{r.strength} vol={r.volatility} struct={r.structure}"
        await db.commit()
    log.info("regime.daily", day=str(target), result=out)
    return out


async def compute_regime_intraday(
    ctx: dict[str, Any], symbols: str | list[str] | None = None
) -> dict[str, Any]:
    """Day type from today's 1-minute bars; runs every 15 minutes during the session."""
    cal = nse_calendar()
    now = utcnow()
    today = now.astimezone(IST).date()
    if not cal.is_trading_day(today):
        return {"skipped": "not a trading day"}
    det = RegimeDetector()
    provider = get_settings().default_market_data_provider
    start, end = _day_bounds(today)
    out: dict[str, Any] = {}
    async with get_session_factory()() as db:
        for sym in _symbols(symbols):
            ins = await get_by_symbol(db, "NSE", sym)
            if ins is None or ins.segment == Segment.OPTIONS:
                continue
            ones = await fetch_candles(db, ins.instrument_id, Timeframe.M1, start, end, provider)
            if not ones:
                out[sym] = "no intraday bars"
                continue
            daily = await latest_daily(db, ins.instrument_id)
            r = det.intraday(ones, daily, now)
            await upsert_intraday(db, ins.instrument_id, r)
            out[sym] = r.day_type
        await db.commit()
    log.info("regime.intraday", result=out)
    return out
