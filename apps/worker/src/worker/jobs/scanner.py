"""Scanner snapshot job: compute every tradable NSE equity/index/future's scanner metrics
from daily bars and store one JSONB snapshot per provider x day. Idempotent."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import get_logger
from core.settings import get_settings
from core.time import IST, utcnow
from market_data.scanner.metrics import compute_universe_metrics
from market_data.scanner.repo import upsert_snapshot

log = get_logger(__name__)


async def compute_scan_snapshot(ctx: dict[str, Any], as_of: str | None = None) -> dict[str, Any]:
    cal = nse_calendar()
    today = utcnow().astimezone(IST).date()
    target = (
        date.fromisoformat(as_of)
        if as_of
        else (today if cal.is_trading_day(today) else cal.previous_trading_day(today))
    )
    provider = get_settings().default_market_data_provider
    async with get_session_factory()() as db:
        rows = await compute_universe_metrics(db, provider=provider, as_of_date=target)
        snap = await upsert_snapshot(db, provider, target, rows)
        await db.commit()
        out = {"as_of": target.isoformat(), "provider": provider, "rows": snap.instrument_count}
    log.info("scanner.snapshot", **out)
    return out
