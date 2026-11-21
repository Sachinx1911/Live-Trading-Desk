"""Option-chain data for DSL `option` operands in paper trading (DSL 1.1, Mark 1 Stage 2).

The strategy engine is synchronous; the database is not. `LiveChain` keeps the stored chain
snapshots of one underlying from the previous day onwards, is refreshed (async) before each bar
is evaluated, and answers the engine synchronously through `at(ts)` with the newest snapshot at
or before `ts`: the same `ChainHistory` logic backtest and replay use (ADR-002).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from core.time import IST, ensure_utc
from market_data.repo.chains import chain_snapshots_between
from strategy.option_features import ChainHistory, ChainView

KEEP_DAYS = 2  # today plus the previous session, for a value at the open


class LiveChain:
    def __init__(self, underlying_instrument_id: int, provider: str | None) -> None:
        self.underlying_instrument_id = underlying_instrument_id
        self.provider = provider
        self._snaps: list[tuple[datetime, Decimal | None, list[dict[str, Any]]]] = []
        self._history = ChainHistory([])

    def at(self, ts: datetime) -> ChainView | None:
        return self._history.at(ts)

    async def refresh(self, db: Any, now: datetime) -> None:
        now = ensure_utc(now)
        since = (
            self._snaps[-1][0] + timedelta(microseconds=1)
            if self._snaps
            else now - timedelta(days=KEEP_DAYS)
        )
        new = await chain_snapshots_between(
            db, self.underlying_instrument_id, since, now, self.provider
        )
        if not new and self._history:
            return
        cutoff_day = (now.astimezone(IST) - timedelta(days=KEEP_DAYS)).date()
        self._snaps = [s for s in [*self._snaps, *new] if s[0].astimezone(IST).date() >= cutoff_day]
        self._history = ChainHistory.from_snapshots(self._snaps)


__all__ = ["LiveChain"]
