"""Option-chain values for the DSL `option` operand (DSL 1.1, Mark 1 Stage 2).

Pure and deterministic. A `ChainView` is one stored chain snapshot of the underlying (nearest
expiry), plus the day's opening OI for `oi_change_from_open`. `ChainHistory` answers, for a
bar time, with the newest view at or before it, never a later one, so backtest, replay and
paper read option data the same way (ADR-002). Missing data gives None, never a guess.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from core.time import IST, ensure_utc
from strategy.dsl.schema import OptionRef

MARKET_OPEN_IST = time(9, 15)
KEEP_STRIKES_EACH_SIDE = 15  # bound memory on long runs; operands reach ATM ± 10

StrikeKey = tuple[float, str]


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


@dataclass(frozen=True)
class ChainView:
    ts: datetime
    spot: float | None
    strikes: tuple[float, ...]  # sorted
    rows: Mapping[StrikeKey, Mapping[str, float | None]]
    open_oi: Mapping[StrikeKey, float] | None = None

    def atm_index(self) -> int | None:
        if self.spot is None or not self.strikes:
            return None
        spot = self.spot
        return min(range(len(self.strikes)), key=lambda i: abs(self.strikes[i] - spot))


def view_from_rows(
    ts: datetime,
    spot: Any,
    rows: Sequence[Mapping[str, Any]],
    open_oi: Mapping[StrikeKey, float] | None = None,
    keep_each_side: int | None = KEEP_STRIKES_EACH_SIDE,
) -> ChainView:
    table: dict[StrikeKey, dict[str, float | None]] = {}
    for r in rows:
        k = _num(r.get("strike"))
        side = r.get("option_type")
        if k is None or side not in ("CE", "PE"):
            continue
        table[(k, str(side))] = {
            f: _num(r.get(f)) for f in ("oi", "iv", "delta", "gamma", "theta", "vega", "ltp")
        }
    strikes = tuple(sorted({k for k, _ in table}))
    view = ChainView(ensure_utc(ts), _num(spot), strikes, table, open_oi)
    i = view.atm_index()
    if keep_each_side is not None and i is not None:
        keep = set(strikes[max(0, i - keep_each_side) : i + keep_each_side + 1])
        table = {k: v for k, v in table.items() if k[0] in keep}
        view = ChainView(view.ts, view.spot, tuple(sorted(keep)), table, open_oi)
    return view


def option_value(ref: OptionRef, view: ChainView | None) -> float | None:
    if view is None:
        return None
    if ref.feature == "pcr":
        put = sum(
            (v.get("oi") or 0)
            for (_, s), v in view.rows.items()
            if s == "PE" and (v.get("oi") or 0) > 0
        )
        call = sum(
            (v.get("oi") or 0)
            for (_, s), v in view.rows.items()
            if s == "CE" and (v.get("oi") or 0) > 0
        )
        return None if call <= 0 else put / call
    i = view.atm_index()
    if i is None:
        return None
    if ref.feature == "iv_atm":
        k = view.strikes[i]
        ivs = [
            x
            for x in (
                view.rows.get((k, "CE"), {}).get("iv"),
                view.rows.get((k, "PE"), {}).get("iv"),
            )
            if x is not None
        ]
        return sum(ivs) / len(ivs) if ivs else None
    j = i + ref.strike_offset
    if j < 0 or j >= len(view.strikes) or ref.side is None:
        return None
    key = (view.strikes[j], ref.side)
    row = view.rows.get(key)
    if row is None:
        return None
    if ref.feature == "oi":
        return row.get("oi")
    if ref.feature == "oi_change_from_open":
        oi = row.get("oi")
        base = view.open_oi.get(key) if view.open_oi is not None else None
        return None if oi is None or base is None else oi - base
    if ref.feature == "greek" and ref.greek is not None:
        return row.get(ref.greek)
    return None


OptionProvider = Callable[[datetime], ChainView | None]


class ChainHistory:
    """Stored chain views of one underlying, sorted by time. `at(ts)` is the newest view at or
    before `ts`. Built from raw snapshots with `from_snapshots`, which also attaches each day's
    opening OI (first snapshot at or after 09:15 IST of that IST day)."""

    def __init__(self, views: Iterable[ChainView]) -> None:
        self._views = sorted(views, key=lambda v: v.ts)
        self._ts = [v.ts for v in self._views]

    def __len__(self) -> int:
        return len(self._views)

    def at(self, ts: datetime) -> ChainView | None:
        i = bisect_right(self._ts, ensure_utc(ts))
        return self._views[i - 1] if i else None

    @classmethod
    def from_snapshots(
        cls, snaps: Iterable[tuple[datetime, Any, Sequence[Mapping[str, Any]]]]
    ) -> ChainHistory:
        ordered = sorted(
            ((ensure_utc(ts), spot, rows) for ts, spot, rows in snaps), key=lambda s: s[0]
        )
        opens: dict[date, dict[StrikeKey, float]] = {}
        views: list[ChainView] = []
        for ts, spot, rows in ordered:
            local = ts.astimezone(IST)
            day = local.date()
            if day not in opens and local.time() >= MARKET_OPEN_IST:
                full = view_from_rows(ts, spot, rows, keep_each_side=None)
                opens[day] = {k: v["oi"] for k, v in full.rows.items() if v.get("oi") is not None}  # type: ignore[misc]
            views.append(view_from_rows(ts, spot, rows, opens.get(day)))
        return cls(views)


def document_uses_options(doc: Any) -> bool:
    """True when any condition of a strategy document reads an `option` operand."""

    def walk(x: Any) -> bool:
        if isinstance(x, dict):
            return x.get("kind") == "option" or any(walk(v) for v in x.values())
        if isinstance(x, list):
            return any(walk(v) for v in x)
        return False

    return walk(doc.model_dump(mode="json") if hasattr(doc, "model_dump") else doc)


__all__ = [
    "ChainHistory",
    "ChainView",
    "OptionProvider",
    "document_uses_options",
    "option_value",
    "view_from_rows",
]
