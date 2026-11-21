"""Market facts for owner rules in simulations (Mark 1, Stage 2).

Backtest and replay run on stored history. `PcrHistory` holds the stored put/call ratio of an
underlying over time and answers, for a simulated moment, with the newest point at or before
it: never a later one (no look-ahead). The same `MarketContext` the paper trader builds from
the database is built here from history, so `pcr_guard` applies in every mode (ADR-002).
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.time import ensure_utc
from risk.owner_rules import MarketContext


@dataclass(frozen=True)
class PcrPoint:
    ts: datetime
    pcr: Decimal | None
    expiry: str  # ISO date of the expiry the PCR was taken from


class PcrHistory:
    """Sorted PCR points of one underlying. `context_at(now)` gives the owner-rule context:
    the last point at or before `now`; before the first point the PCR is missing, which the
    rule treats like the paper trader does (no data, no option buy)."""

    def __init__(self, points: Iterable[PcrPoint]) -> None:
        self._points = sorted(
            (PcrPoint(ensure_utc(p.ts), p.pcr, p.expiry) for p in points), key=lambda p: p.ts
        )
        self._ts = [p.ts for p in self._points]

    def __len__(self) -> int:
        return len(self._points)

    @property
    def first_ts(self) -> datetime | None:
        return self._ts[0] if self._ts else None

    @property
    def last_ts(self) -> datetime | None:
        return self._ts[-1] if self._ts else None

    def point_at(self, now: datetime) -> PcrPoint | None:
        i = bisect_right(self._ts, ensure_utc(now))
        return self._points[i - 1] if i else None

    def context_at(self, now: datetime) -> MarketContext:
        now = ensure_utc(now)
        p = self.point_at(now)
        if p is None:
            return MarketContext(now=now)
        return MarketContext(now=now, pcr=p.pcr, pcr_ts=p.ts, pcr_expiry=p.expiry)


__all__ = ["PcrHistory", "PcrPoint"]
