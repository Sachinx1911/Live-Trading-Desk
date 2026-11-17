"""Nightly NSE reference import (ADR-011): holidays, corporate actions, F&O lot sizes.
Each part is isolated: a failure is logged and reported, the others still run."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core.calendar import nse_calendar
from core.db import get_session_factory
from core.logging import get_logger
from core.time import IST, utcnow
from providers.nse import NseClient, parse_fo_bhavcopy, parse_holidays
from providers.nse.importer import import_corporate_actions, import_fo_lot_sizes, import_holidays

log = get_logger(__name__)


async def import_nse_reference(ctx: dict[str, Any], date_str: str | None = None) -> dict[str, Any]:
    cal = nse_calendar()
    today = utcnow().astimezone(IST).date()
    trade_date = date.fromisoformat(date_str) if date_str else cal.previous_trading_day(today)
    summary: dict[str, Any] = {"trade_date": trade_date.isoformat()}

    async with NseClient() as client, get_session_factory()() as db:
        # 1. Holidays (NSE serves the current year; next year appears late in the year).
        try:
            payload = await client.fetch_holidays(today.year)
            counts = await import_holidays(db, parse_holidays(payload))
            await db.commit()
            summary["holidays"] = counts.as_dict()
        except Exception as exc:
            await db.rollback()
            summary["holidays"] = {"error": str(exc)}
            log.warning("nse.holidays.failed", error=str(exc))

        # 2. Corporate actions, trailing 30 days.
        try:
            rows = await client.fetch_corporate_actions(today - timedelta(days=30), today)
            counts = await import_corporate_actions(db, rows)
            await db.commit()
            summary["corporate_actions"] = counts.as_dict()
        except Exception as exc:
            await db.rollback()
            summary["corporate_actions"] = {"error": str(exc)}
            log.warning("nse.corporate_actions.failed", error=str(exc))

        # 3. Lot sizes from the F&O bhavcopy of the trade date.
        try:
            blob = await client.fetch_fo_bhavcopy(trade_date)
            counts = await import_fo_lot_sizes(db, trade_date, parse_fo_bhavcopy(blob))
            await db.commit()
            summary["lot_sizes"] = counts.as_dict()
        except Exception as exc:
            await db.rollback()
            summary["lot_sizes"] = {"error": str(exc)}
            log.warning("nse.lot_sizes.failed", error=str(exc), trade_date=trade_date.isoformat())

    await ctx["redis"].set("nse_reference:last_run", utcnow().isoformat(), ex=3 * 24 * 3600)
    log.info("nse.reference.done", **{k: v for k, v in summary.items() if k != "trade_date"})
    return summary
