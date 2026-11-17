"""Market data jobs: instrument sync, historical backfill, end-of-day gap report."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import get_logger
from core.models import Timeframe
from core.secrets import SecretBox
from core.services.brokers import BrokerService
from core.settings import get_settings
from core.time import IST, ensure_utc, utcnow
from market_data.backfill import backfill_candles
from market_data.binding import bind_provider
from market_data.quality import gap_report
from market_data.repo.instruments import get_by_symbol
from market_data.sync import sync_instrument_master
from providers.base import ConnectionState, MarketDataProvider
from providers.registry import create as create_provider

log = get_logger(__name__)


async def _provider() -> MarketDataProvider:
    s = get_settings()
    if s.default_market_data_provider != "upstox":
        return create_provider(s.default_market_data_provider)
    from providers.upstox.provider import UpstoxMarketDataProvider

    token: str | None = None
    try:
        box = SecretBox(s.secrets_key.get_secret_value())
        from sqlalchemy import select

        from core.db.models import Broker, BrokerAccount

        async with get_session_factory()() as db:
            svc = BrokerService(db, s, box)
            rows = await db.execute(
                select(BrokerAccount).join(Broker).where(Broker.code == "upstox")
            )
            acct = rows.scalars().first()
            if acct:
                token = await svc.valid_token(acct.id)
            await db.commit()
    except ValueError:
        pass
    return UpstoxMarketDataProvider(access_token_getter=lambda: token)


async def sync_instruments(ctx: dict[str, Any]) -> dict[str, int]:
    p = await _provider()
    if (await p.health()).state == ConnectionState.AUTH_REQUIRED:
        log.warning("sync_instruments.skipped", reason="auth_required")
        return {}
    async with get_session_factory()() as db:
        res = await sync_instrument_master(p, db)
        await db.commit()
    return {"new": res.new, "updated": res.updated, "unchanged": res.unchanged}


async def backfill_instrument(
    ctx: dict[str, Any], symbol: str, timeframe: str, start: str, end: str | None = None
) -> dict[str, Any]:
    """Backfill one instrument. `start`/`end` are ISO dates (IST days)."""
    p = await _provider()
    tf = Timeframe(timeframe)
    s_dt = ensure_utc(datetime.fromisoformat(start).replace(tzinfo=IST))
    e_dt = ensure_utc(datetime.fromisoformat(end).replace(tzinfo=IST)) if end else utcnow()
    async with get_session_factory()() as db:
        await bind_provider(db, p)
        ins = await get_by_symbol(db, "NSE", symbol.upper())
        if ins is None:
            return {"error": f"unknown symbol {symbol}"}
        res = await backfill_candles(p, db, ins.instrument_id, tf, s_dt, e_dt)
        await db.commit()
    log.info("backfill.done", symbol=symbol, timeframe=timeframe, rows=res.rows, chunks=res.chunks)
    return {"rows": res.rows, "chunks": res.chunks}


async def eod_gap_report(ctx: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    cal = nse_calendar()
    d = datetime.fromisoformat(day).date() if day else utcnow().astimezone(IST).date()
    if not cal.is_trading_day(d):
        return {"skipped": "not a trading day"}
    s = get_settings()
    symbols = [
        x.strip().upper()
        for x in (ctx.get("collect_symbols") or "NIFTY,BANKNIFTY,INDIAVIX").split(",")
    ]
    out: dict[str, Any] = {}
    async with get_session_factory()() as db:
        for sym in symbols:
            ins = await get_by_symbol(db, "NSE", sym)
            if ins is None:
                continue
            rep = await gap_report(
                db, ins.instrument_id, d, s.default_market_data_provider, cal, persist=True
            )
            out[sym] = {"missing": rep.missing, "coverage_pct": round(rep.coverage_pct, 2)}
        await db.commit()
    log.info("eod_gap_report", day=str(d), report=out)
    return out


__all__ = ["backfill_instrument", "eod_gap_report", "sync_instruments", "timedelta"]
