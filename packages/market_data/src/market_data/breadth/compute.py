"""Market breadth from daily closes (pure, Polars). No I/O; the job loads bars and stores rows.

Definitions (one universe, one trading day `d`, one provider):
- universe_size: members with a daily bar on `d`.
- advances / declines / unchanged: members whose close on `d` is above / below / equal to
  their previous stored close. Members without a previous close are in none of the three.
- new_52w_high / new_52w_low: close on `d` strictly above / below every close of the previous
  251 sessions (252-session window, close basis). Needs 252 bars; fewer -> not counted.
- above_ema50_pct / above_ema200_pct: share (0-100, 2 dp) of members with a valid EMA on `d`
  whose close is above it. EMA = `strategy.indicators` EMA (SMA seed, TradingView/TA-Lib).
  None when no member has enough history.
- index_moves: {symbol: {close, prev_close, change, change_pct}} for the index symbols.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import polars as pl

from strategy.indicators.library import EMA

WINDOW_52W = 252
EMA_FAST = 50
EMA_SLOW = 200
BAR_COLUMNS = ("symbol", "day", "close")


@dataclass(frozen=True)
class BreadthRow:
    as_of_date: date
    universe_size: int
    advances: int
    declines: int
    unchanged: int
    new_52w_high: int
    new_52w_low: int
    above_ema50_pct: float | None
    above_ema200_pct: float | None
    index_moves: dict[str, dict[str, float | None]] = field(default_factory=dict)
    missing: tuple[str, ...] = ()  # universe members with no bar on the day

    def as_dict(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "universe_size": self.universe_size,
            "advances": self.advances,
            "declines": self.declines,
            "unchanged": self.unchanged,
            "new_52w_high": self.new_52w_high,
            "new_52w_low": self.new_52w_low,
            "above_ema50_pct": self.above_ema50_pct,
            "above_ema200_pct": self.above_ema200_pct,
            "index_moves": self.index_moves,
            "missing": list(self.missing),
        }


def bars_frame(rows: Iterable[tuple[str, date, float]]) -> pl.DataFrame:
    data = list(rows)
    return pl.DataFrame(
        {
            "symbol": [r[0] for r in data],
            "day": [r[1] for r in data],
            "close": [float(r[2]) for r in data],
        },
        schema={"symbol": pl.String, "day": pl.Date, "close": pl.Float64},
    )


def prepare(bars: pl.DataFrame) -> pl.DataFrame:
    """Add prev_close, ema50, ema200 and the prior-251-session max/min close per symbol.
    EMAs are causal, so computing once over the full history equals computing per day."""
    if bars.is_empty():
        return bars.with_columns(
            *(
                pl.lit(None, dtype=pl.Float64).alias(c)
                for c in ("prev_close", "ema50", "ema200", "prior_max", "prior_min")
            )
        )
    parts: list[pl.DataFrame] = []
    for part in bars.sort("symbol", "day").partition_by("symbol", maintain_order=True):
        ema50 = EMA().compute(part, period=EMA_FAST)["value"]
        ema200 = EMA().compute(part, period=EMA_SLOW)["value"]
        prev = part["close"].shift(1)
        parts.append(
            part.with_columns(
                prev.alias("prev_close"),
                ema50.fill_nan(None).alias("ema50"),
                ema200.fill_nan(None).alias("ema200"),
                prev.rolling_max(WINDOW_52W - 1).alias("prior_max"),
                prev.rolling_min(WINDOW_52W - 1).alias("prior_min"),
            )
        )
    return pl.concat(parts)


def _pct(num: int, den: int) -> float | None:
    return None if den == 0 else round(num * 100.0 / den, 2)


def _r(v: float | None, nd: int = 2) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, nd)


def index_moves(
    prepared_index: pl.DataFrame, day: date, symbols: Sequence[str]
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    today = prepared_index.filter(pl.col("day") == day)
    for sym in symbols:
        row = today.filter(pl.col("symbol") == sym)
        if row.is_empty():
            continue
        close = float(row["close"][0])
        prev = row["prev_close"][0]
        change = None if prev is None else close - float(prev)
        pct = None if prev in (None, 0) or change is None else change / float(prev) * 100.0
        out[sym] = {
            "close": _r(close),
            "prev_close": _r(None if prev is None else float(prev)),
            "change": _r(change),
            "change_pct": _r(pct),
        }
    return out


def breadth_for_day(
    prepared: pl.DataFrame,
    day: date,
    members: Sequence[str],
    *,
    prepared_index: pl.DataFrame | None = None,
    index_symbols: Sequence[str] = (),
) -> BreadthRow:
    rows = prepared.filter((pl.col("day") == day) & pl.col("symbol").is_in(list(members)))
    present = set(rows["symbol"].to_list())
    both = rows.filter(pl.col("prev_close").is_not_null())
    adv = both.filter(pl.col("close") > pl.col("prev_close")).height
    dec = both.filter(pl.col("close") < pl.col("prev_close")).height
    unch = both.height - adv - dec
    full = rows.filter(pl.col("prior_max").is_not_null())
    hi = full.filter(pl.col("close") > pl.col("prior_max")).height
    lo = full.filter(pl.col("close") < pl.col("prior_min")).height
    e50 = rows.filter(pl.col("ema50").is_not_null())
    e200 = rows.filter(pl.col("ema200").is_not_null())
    moves = (
        index_moves(prepared_index, day, index_symbols)
        if prepared_index is not None and index_symbols
        else {}
    )
    return BreadthRow(
        as_of_date=day,
        universe_size=rows.height,
        advances=adv,
        declines=dec,
        unchanged=unch,
        new_52w_high=hi,
        new_52w_low=lo,
        above_ema50_pct=_pct(e50.filter(pl.col("close") > pl.col("ema50")).height, e50.height),
        above_ema200_pct=_pct(e200.filter(pl.col("close") > pl.col("ema200")).height, e200.height),
        index_moves=moves,
        missing=tuple(sorted(set(members) - present)),
    )


def breadth_range(
    bars: pl.DataFrame,
    days: Sequence[date],
    members: Sequence[str],
    *,
    index_bars: pl.DataFrame | None = None,
    index_symbols: Sequence[str] = (),
) -> list[BreadthRow]:
    """Breadth for each day that has at least one member bar (days without any are skipped)."""
    prepared = prepare(bars)
    prepared_index = prepare(index_bars) if index_bars is not None else None
    out: list[BreadthRow] = []
    for d in days:
        row = breadth_for_day(
            prepared, d, members, prepared_index=prepared_index, index_symbols=index_symbols
        )
        if row.universe_size > 0:
            out.append(row)
    return out
