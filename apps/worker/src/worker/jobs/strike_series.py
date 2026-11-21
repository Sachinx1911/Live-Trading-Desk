"""Rebuild the derived per-strike option series (Mark 1, 1.1) for one underlying and IST day
from the raw chain snapshots. Enqueued on demand (after a fix to the derivation, or to fill a
day the collector could not derive); idempotent."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.db import get_session_factory
from core.logging import get_logger
from market_data.repo.instruments import get_by_symbol
from market_data.strike_series import rebuild_strike_series

log = get_logger(__name__)


async def rebuild_strike_series_job(
    ctx: dict[str, Any], symbol: str, day: str, exchange: str = "NSE"
) -> dict[str, Any]:
    """`symbol` is the underlying (e.g. NIFTY), `day` an ISO date in IST."""
    d = date.fromisoformat(day)
    async with get_session_factory()() as db:
        inst = await get_by_symbol(db, exchange, symbol.upper())
        if inst is None:
            return {"ok": False, "error": f"unknown instrument {exchange}:{symbol}"}
        rows = await rebuild_strike_series(db, inst.instrument_id, d)
        await db.commit()
    log.info("strike_series.rebuilt", symbol=symbol, day=day, rows=rows)
    return {"ok": True, "symbol": symbol.upper(), "day": day, "rows": rows}
