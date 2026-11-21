"""Proactive alerts (Mark 1 Stage 3.2): every minute 09:00-15:45 IST on NSE trading days.
Evaluates the rules in protocols.alerts, stores new alerts (dedup window), and delivers them
and any `pending` ones (written by the paper trader) via Telegram when configured."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import get_logger
from core.notify import build_notifier
from core.settings import get_settings
from core.time import IST, utcnow
from protocols.alert_store import (
    deliver,
    gather_facts,
    params_from,
    pending_alerts,
    store_alerts,
    telegram_configured,
)
from protocols.alerts import evaluate
from worker.jobs.protocols import secret_box

log = get_logger(__name__)

WINDOW_START = time(9, 0)
WINDOW_END = time(15, 45)


def in_alert_window(now: datetime) -> bool:
    local = now.astimezone(IST)
    return nse_calendar().is_trading_day(local.date()) and (
        WINDOW_START <= local.time() <= WINDOW_END
    )


async def evaluate_alerts(ctx: dict[str, Any], force_market_hours: bool = False) -> dict[str, Any]:
    """`force_market_hours` evaluates as if the session were open (manual checks only)."""
    now = utcnow()
    if not force_market_hours and not in_alert_window(now):
        return {"skipped": "outside 09:00-15:45 IST on a trading day"}
    settings = get_settings()
    notifier = build_notifier(settings)
    market_open = force_market_hours or nse_calendar().is_open(now)
    async with get_session_factory()() as db:
        facts = await gather_facts(
            db,
            ctx["redis"],
            settings,
            now=now,
            market_open=market_open,
            secret_box=secret_box(settings),
            notifier=notifier,
        )
        candidates = evaluate(facts, params_from(settings))
        stored = await store_alerts(
            db, candidates, now=now, window=timedelta(minutes=settings.alert_dedup_minutes)
        )
        pending = await pending_alerts(db)
        counts = await deliver(
            [*stored, *pending], notifier, configured=telegram_configured(settings)
        )
        await db.commit()
    out = {
        "market_open": market_open,
        "candidates": len(candidates),
        "stored": [a.dedup_key for a in stored],
        "pending_delivered": len(pending),
        "telegram": counts,
    }
    log.info("alerts.evaluated", **out)
    return out
