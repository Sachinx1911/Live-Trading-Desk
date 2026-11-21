"""Keep stored candles current after each session (found missing 2026-11-21: daily candles for
18-20 Nov were never fetched because `eod_gap_report` only reports gaps).

`refresh_daily_candles` re-fetches recent 1d candles for every instrument we already keep daily
history for (the scanner / regime / breadth universe), every NIFTY 50 member and the
collector's symbols, and the
official 1-minute candles of the collector's symbols for the last few sessions so collector
downtime is repaired from the provider. Upserts are idempotent; candles stay single-provider.
Runs after the close and before the regime, scanner and breadth jobs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.db.models import HistoricalCandle
from core.logging import get_logger
from core.models import Timeframe
from core.settings import get_settings
from core.time import IST, utcnow
from market_data.backfill import backfill_candles
from market_data.binding import bind_provider
from market_data.breadth.universe import INDEX_SYMBOLS, NIFTY50
from market_data.repo._lookup import provider_id
from market_data.repo.instruments import get_by_symbol
from providers.base import ConnectionState
from worker.jobs.market_data import _provider

log = get_logger(__name__)

DAILY_LOOKBACK_DAYS = 10
MINUTE_LOOKBACK_SESSIONS = 3


async def refresh_daily_candles(
    ctx: dict[str, Any], daily_days: int = DAILY_LOOKBACK_DAYS
) -> dict[str, Any]:
    s = get_settings()
    p = await _provider()
    if (await p.health()).state == ConnectionState.AUTH_REQUIRED:
        log.warning("daily_refresh.skipped", reason="auth_required")
        return {"skipped": "broker login required"}
    cal = nse_calendar()
    now = utcnow()
    today = now.astimezone(IST).date()
    d_start = datetime.combine(today - timedelta(days=daily_days), datetime.min.time(), IST)
    sessions: list[Any] = []
    d = today if cal.is_trading_day(today) else cal.previous_trading_day(today)
    while len(sessions) < MINUTE_LOOKBACK_SESSIONS:
        sessions.append(d)
        d = cal.previous_trading_day(d)
    m_start = datetime.combine(sessions[-1], datetime.min.time(), IST)

    out: dict[str, Any] = {"daily": 0, "minute": 0, "errors": {}}
    async with get_session_factory()() as db:
        await bind_provider(db, p)
        pid = await provider_id(db, s.default_market_data_provider)
        since = now - timedelta(days=30)
        universe = set(
            (
                await db.execute(
                    select(HistoricalCandle.instrument_id)
                    .where(
                        HistoricalCandle.provider_id == pid,
                        HistoricalCandle.timeframe == Timeframe.D1,
                        HistoricalCandle.ts >= since,
                    )
                    .distinct()
                )
            ).scalars()
        )
        collect: list[int] = []
        for sym in (x.strip().upper() for x in s.collect_symbols.split(",") if x.strip()):
            ins = await get_by_symbol(db, "NSE", sym)
            if ins is not None:
                collect.append(ins.instrument_id)
        universe.update(collect)
        # NIFTY 50 members and indices even when no daily candle is stored yet (breadth).
        for sym in (*NIFTY50, *INDEX_SYMBOLS):
            ins = await get_by_symbol(db, "NSE", sym)
            if ins is not None:
                universe.add(ins.instrument_id)
        for iid in sorted(universe):
            try:
                res = await backfill_candles(p, db, iid, Timeframe.D1, d_start, now)
                out["daily"] += res.rows
                await db.commit()
            except Exception as exc:
                await db.rollback()
                out["errors"][f"{iid}:1d"] = str(exc)[:200]
        for iid in collect:
            try:
                res = await backfill_candles(p, db, iid, Timeframe.M1, m_start, now)
                out["minute"] += res.rows
                await db.commit()
            except Exception as exc:
                await db.rollback()
                out["errors"][f"{iid}:1m"] = str(exc)[:200]
    out["instruments"] = len(universe)
    log.info(
        "daily_refresh.done",
        **{k: v for k, v in out.items() if k != "errors"},
        errors=len(out["errors"]),
    )
    return out
