"""Daily market breadth (Mark 1 Stage 3.6) after the close, plus a rebuild over a range.

Uses only the active provider's daily candles (DEFAULT_MARKET_DATA_PROVIDER), never a mix.
The first daily run with an empty table back-fills the last 60 trading days; later runs
recompute the last 10 sessions (idempotent upsert), so daily candles that arrive late, e.g.
from the daily candle refresh, are picked up without a manual rebuild."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import get_logger
from core.settings import get_settings
from core.time import IST, utcnow
from market_data.breadth.repo import count_rows
from market_data.breadth.service import compute_and_store

log = get_logger(__name__)

DEFAULT_UNIVERSE = "NIFTY50"
BACKFILL_SESSIONS = 60
RECOMPUTE_SESSIONS = 10


def _latest_session() -> date:
    cal = nse_calendar()
    today = utcnow().astimezone(IST).date()
    return today if cal.is_trading_day(today) else cal.previous_trading_day(today)


def _sessions_back(end: date, n: int) -> date:
    cal = nse_calendar()
    d = end
    for _ in range(n - 1):
        d = cal.previous_trading_day(d)
    return d


async def compute_market_breadth(
    ctx: dict[str, Any], day: str | None = None, universe: str = DEFAULT_UNIVERSE
) -> dict[str, Any]:
    target = date.fromisoformat(day) if day else _latest_session()
    provider = get_settings().default_market_data_provider
    async with get_session_factory()() as db:
        first = await count_rows(db, provider=provider, universe=universe) == 0
        start = _sessions_back(target, BACKFILL_SESSIONS if first else RECOMPUTE_SESSIONS)
        run = await compute_and_store(
            db, provider=provider, universe=universe, start=start, end=target
        )
        await db.commit()
    out = run.summary() | {"backfill": first}
    log.info("breadth.daily", days=out["days"], to=out["to"], backfill=first, provider=provider)
    return out


async def rebuild_market_breadth(
    ctx: dict[str, Any],
    from_date: str,
    to_date: str | None = None,
    universe: str = DEFAULT_UNIVERSE,
) -> dict[str, Any]:
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date) if to_date else _latest_session()
    if end < start:
        raise ValueError("to_date before from_date")
    provider = get_settings().default_market_data_provider
    async with get_session_factory()() as db:
        run = await compute_and_store(
            db, provider=provider, universe=universe, start=start, end=end
        )
        await db.commit()
    out = run.summary()
    log.info("breadth.rebuild", days=out["days"], start=out["from"], end=out["to"])
    return out
