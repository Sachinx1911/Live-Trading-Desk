"""Market breadth math (pure): hand-checked cases plus hypothesis invariants."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from market_data.breadth.compute import (
    WINDOW_52W,
    bars_frame,
    breadth_for_day,
    breadth_range,
    prepare,
)
from market_data.breadth.universe import INDEX_SYMBOLS, NIFTY50, universe_symbols
from strategy.indicators.library import _ema

D0 = date(2025, 1, 1)


def _days(n: int) -> list[date]:
    return [D0 + timedelta(days=i) for i in range(n)]


def _frame(series: dict[str, list[float]], days: list[date] | None = None) -> pl.DataFrame:
    rows = []
    for sym, closes in series.items():
        ds = days or _days(len(closes))
        rows += [(sym, ds[i], c) for i, c in enumerate(closes)]
    return bars_frame(rows)


def test_advances_declines_unchanged_and_missing() -> None:
    bars = _frame({"A": [10, 11], "B": [10, 9], "C": [10, 10], "D": [5]})
    day = D0 + timedelta(days=1)
    r = breadth_for_day(prepare(bars), day, ["A", "B", "C", "D", "E"])
    assert (r.universe_size, r.advances, r.declines, r.unchanged) == (3, 1, 1, 1)
    assert r.missing == ("D", "E")
    assert r.above_ema50_pct is None and r.above_ema200_pct is None
    assert r.new_52w_high == 0 and r.new_52w_low == 0  # not enough history


def test_new_52w_high_low_need_full_window_and_strict_break() -> None:
    flat = [100.0] * (WINDOW_52W - 1)
    bars = _frame(
        {
            "UP": [*flat, 101.0],  # strictly above the prior 251 closes
            "DN": [*flat, 99.0],
            "EQ": [*flat, 100.0],  # ties are not new highs
            "SHORT": [*flat[:-1], 120.0],  # 251 bars only
        },
        _days(WINDOW_52W),
    )
    last = D0 + timedelta(days=WINDOW_52W - 1)
    r = breadth_for_day(prepare(bars), last, ["UP", "DN", "EQ", "SHORT"])
    assert (r.new_52w_high, r.new_52w_low) == (1, 1)


def test_short_series_gets_no_52w_flag() -> None:
    n = WINDOW_52W - 1
    bars = _frame({"S": [100.0] * (n - 1) + [120.0]}, _days(n))
    r = breadth_for_day(prepare(bars), D0 + timedelta(days=n - 1), ["S"])
    assert r.new_52w_high == 0


def test_ema_percentages_match_reference_ema() -> None:
    rng = np.random.default_rng(3)
    series = {f"S{i}": list(100 + np.cumsum(rng.normal(0, 1, 260))) for i in range(6)}
    bars = _frame(series)
    last = D0 + timedelta(days=259)
    r = breadth_for_day(prepare(bars), last, list(series))
    above50 = sum(v[-1] > _ema(np.array(v), 50)[-1] for v in series.values())
    above200 = sum(v[-1] > _ema(np.array(v), 200)[-1] for v in series.values())
    assert r.above_ema50_pct == round(above50 * 100 / 6, 2)
    assert r.above_ema200_pct == round(above200 * 100 / 6, 2)


def test_index_moves() -> None:
    idx = _frame({"NIFTY": [24000.0, 24240.0], "INDIAVIX": [12.0, 11.4]})
    eq = _frame({"A": [1.0, 2.0]})
    rows = breadth_range(
        eq, [D0 + timedelta(days=1)], ["A"], index_bars=idx, index_symbols=INDEX_SYMBOLS
    )
    moves = rows[0].index_moves
    assert moves["NIFTY"] == {
        "close": 24240.0,
        "prev_close": 24000.0,
        "change": 240.0,
        "change_pct": 1.0,
    }
    assert moves["INDIAVIX"]["change_pct"] == -5.0
    assert "BANKNIFTY" not in moves  # no data -> absent, never invented


def test_range_skips_days_without_member_bars() -> None:
    bars = _frame({"A": [1.0, 2.0, 3.0]})
    days = [*_days(3), D0 + timedelta(days=10)]
    assert [r.as_of_date for r in breadth_range(bars, days, ["A"])] == _days(3)


def test_universe_lookup() -> None:
    assert len(NIFTY50) == 50 and len(set(NIFTY50)) == 50
    assert universe_symbols("nifty50") == NIFTY50


closes = st.lists(
    st.one_of(st.none(), st.integers(min_value=1, max_value=20).map(float)),
    min_size=1,
    max_size=12,
)


@settings(max_examples=150, deadline=None)
@given(st.dictionaries(st.sampled_from(list("ABCDEFGH")), closes, min_size=1, max_size=8))
def test_breadth_invariants(data: dict[str, list[float | None]]) -> None:
    """None = no bar that day (gaps). Invariants hold on every day."""
    days = _days(12)
    rows = [(s, days[i], c) for s, cs in data.items() for i, c in enumerate(cs) if c is not None]
    if not rows:
        return
    bars = bars_frame(rows)
    prepared = prepare(bars)
    members = sorted(data)
    for d in days:
        r = breadth_for_day(prepared, d, members)
        today = {s for s, dd, _ in rows if dd == d}
        with_prev = {s for s in today if any(dd < d for ss, dd, _ in rows if ss == s)}
        assert r.universe_size == len(today)
        assert r.advances + r.declines + r.unchanged == len(with_prev)
        assert min(r.advances, r.declines, r.unchanged) >= 0
        assert r.new_52w_high + r.new_52w_low <= r.universe_size
        for pct in (r.above_ema50_pct, r.above_ema200_pct):
            assert pct is None or 0.0 <= pct <= 100.0
        assert set(r.missing) == set(members) - today


@settings(max_examples=25, deadline=None)
@given(
    st.integers(min_value=0, max_value=2**31 - 1),
    st.integers(min_value=1, max_value=8),
    st.integers(min_value=40, max_value=270),
)
def test_long_series_percentages_and_52w(seed: int, n_sym: int, length: int) -> None:
    rng = np.random.default_rng(seed)
    series = {
        f"S{i}": [float(x) for x in np.round(100 + np.cumsum(rng.normal(0, 2, length)), 1)]
        for i in range(n_sym)
    }
    prepared = prepare(_frame(series))
    last = D0 + timedelta(days=length - 1)
    r = breadth_for_day(prepared, last, list(series))
    assert r.universe_size == n_sym
    assert r.advances + r.declines + r.unchanged == n_sym
    for pct, period in ((r.above_ema50_pct, 50), (r.above_ema200_pct, 200)):
        if length < period:
            assert pct is None
        else:
            assert pct is not None and 0.0 <= pct <= 100.0
    if length < WINDOW_52W:
        assert r.new_52w_high == 0 and r.new_52w_low == 0
    else:
        hi = sum(v[-1] > max(v[-WINDOW_52W:-1]) for v in series.values())
        lo = sum(v[-1] < min(v[-WINDOW_52W:-1]) for v in series.values())
        assert (r.new_52w_high, r.new_52w_low) == (hi, lo)
