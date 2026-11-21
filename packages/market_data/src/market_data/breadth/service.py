"""Compute and store breadth for a date range (used by the daily and rebuild jobs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import polars as pl
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models._enums import InstrumentType
from market_data.breadth.compute import BreadthRow, breadth_range
from market_data.breadth.repo import WARMUP_DAYS, load_closes, upsert_rows
from market_data.breadth.universe import INDEX_SYMBOLS, universe_symbols


@dataclass
class BreadthRun:
    provider: str
    universe: str
    start: date
    end: date
    rows: list[BreadthRow] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        last = self.rows[-1] if self.rows else None
        return {
            "provider": self.provider,
            "universe": self.universe,
            "from": self.start.isoformat(),
            "to": self.end.isoformat(),
            "days": len(self.rows),
            "latest": last.as_dict() if last else None,
        }


async def compute_and_store(
    session: AsyncSession, *, provider: str, universe: str, start: date, end: date
) -> BreadthRun:
    """Days = dates in `start..end` on which at least one member has a daily bar from
    `provider`. Idempotent (upsert keyed by date, universe, provider)."""
    members = universe_symbols(universe)
    load_from = start - timedelta(days=WARMUP_DAYS)
    bars = await load_closes(session, provider=provider, symbols=members, start=load_from, end=end)
    idx = await load_closes(
        session,
        provider=provider,
        symbols=INDEX_SYMBOLS,
        start=start - timedelta(days=15),
        end=end,
        instrument_types=(InstrumentType.INDEX,),
    )
    days = sorted(
        set(bars.filter((pl.col("day") >= start) & (pl.col("day") <= end))["day"].to_list())
    )
    rows = breadth_range(bars, days, members, index_bars=idx, index_symbols=INDEX_SYMBOLS)
    await upsert_rows(session, provider=provider, universe=universe, rows=rows)
    return BreadthRun(provider=provider, universe=universe, start=start, end=end, rows=rows)
