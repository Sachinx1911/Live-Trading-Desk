"""Scanner: metrics on synthetic daily bars, the filter engine, and preset validity."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from market_data.scanner.filters import FIELDS, ScanQuery, ScanQueryError, apply_query
from market_data.scanner.metrics import MIN_BARS, ScanInstrument, metrics_for_instrument
from market_data.scanner.presets import PRESETS, validate_presets

AS_OF = date(2026, 11, 18)


def _bars(n: int, drift: float, start: float = 100.0, oi: bool = False) -> pl.DataFrame:
    rng = np.random.default_rng(7)
    close = start * np.cumprod(1 + drift + rng.normal(0, 0.005, n))
    opn = np.concatenate([[start], close[:-1]]) * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(opn, close) * 1.01
    low = np.minimum(opn, close) * 0.99
    vol = rng.integers(1_000, 2_000, n).astype(float)
    vol[-1] = 10_000  # volume shock on the last bar
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        {
            "ts": [t0 + timedelta(days=i) for i in range(n)],
            "open": opn,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
            "oi": (np.arange(n, dtype=float) + 1000) if oi else [float("nan")] * n,
        }
    )


def _ins(iid: int, sym: str, seg: str = "equity") -> ScanInstrument:
    return ScanInstrument(iid, sym, sym.title(), seg, 1)


def _rows() -> list[dict]:
    up = metrics_for_instrument(
        _ins(1, "UPTREND"),
        _bars(260, 0.004),
        AS_OF,
        {"trend": "up", "strength": "strong", "volatility": "normal", "structure": "bullish"},
    )
    dn = metrics_for_instrument(_ins(2, "DOWNTREND"), _bars(260, -0.004), AS_OF)
    fut = metrics_for_instrument(
        ScanInstrument(3, "NIFTYFUT", "Nifty fut", "futures", 65, "NIFTY", AS_OF),
        _bars(120, 0.001, oi=True),
        AS_OF,
    )
    assert up and dn and fut
    return [up, dn, fut]


def test_metrics_shape_and_direction() -> None:
    up, dn, fut = _rows()
    assert set(up) >= set(FIELDS) | {"instrument_id", "as_of"}
    assert up["ema_alignment"] == "bull" and dn["ema_alignment"] == "bear"
    assert up["change_20d_pct"] > 0 > dn["change_20d_pct"]
    assert up["rsi14"] > 50 > dn["rsi14"]
    assert up["rel_volume"] > 2
    assert up["dist_52w_high_pct"] <= 0 and up["dist_52w_low_pct"] >= 0
    assert up["regime_trend"] == "up" and dn["regime_trend"] is None
    assert fut["oi"] == 1119 and fut["oi_change_1d_pct"] == pytest.approx(100 / 1118, rel=1e-3)
    assert (
        fut["ema200"] is None
        and fut["underlying"] == "NIFTY"
        and fut["expiry"] == AS_OF.isoformat()
    )
    assert up["bars"] == 260 and up["as_of"] == AS_OF.isoformat()


def test_insufficient_history_returns_none() -> None:
    assert metrics_for_instrument(_ins(9, "NEW"), _bars(MIN_BARS - 1, 0.0), AS_OF) is None


def test_filter_all_any_between_in_sort_page() -> None:
    rows = _rows()
    q = ScanQuery.from_dict(
        {
            "filters": {
                "all": [
                    {"field": "segment", "op": "eq", "value": "equity"},
                    {"field": "rsi14", "op": "gt", "value": 50},
                ]
            }
        }
    )
    out, total = apply_query(rows, q)
    assert total == 1 and out[0]["symbol"] == "UPTREND"
    q = ScanQuery.from_dict(
        {
            "filters": {
                "any": [
                    {"field": "symbol", "op": "contains", "value": "down"},
                    {"field": "segment", "op": "in", "value": ["futures"]},
                ]
            },
            "sort": {"field": "symbol", "dir": "asc"},
        }
    )
    out, total = apply_query(rows, q)
    assert [r["symbol"] for r in out] == ["DOWNTREND", "NIFTYFUT"]
    q = ScanQuery.from_dict(
        {
            "filters": {"all": [{"field": "rsi14", "op": "between", "value": [0, 100]}]},
            "sort": {"field": "change_20d_pct", "dir": "desc"},
            "limit": 1,
            "offset": 1,
            "columns": ["symbol", "change_20d_pct"],
        }
    )
    out, total = apply_query(rows, q)
    assert (
        total == 3
        and len(out) == 1
        and set(out[0]) == {"instrument_id", "symbol", "change_20d_pct"}
    )
    # null regime never matches an eq filter and sorts last
    q = ScanQuery.from_dict(
        {"filters": {"all": [{"field": "regime_trend", "op": "eq", "value": "up"}]}}
    )
    assert apply_query(rows, q)[1] == 1
    assert apply_query([], q) == ([], 0)


def test_bad_specs_rejected() -> None:
    with pytest.raises(ScanQueryError):
        ScanQuery.from_dict({"filters": {"all": [{"field": "nope", "op": "eq", "value": 1}]}})
    with pytest.raises(ScanQueryError):
        ScanQuery.from_dict({"filters": {"all": [{"field": "symbol", "op": "gt", "value": 1}]}})
    with pytest.raises(ScanQueryError):
        ScanQuery.from_dict(
            {"filters": {"all": [{"field": "rsi14", "op": "between", "value": [1]}]}}
        )
    with pytest.raises(ScanQueryError):
        ScanQuery.from_dict({"sort": {"field": "rsi14", "dir": "sideways"}})
    with pytest.raises(ScanQueryError):
        ScanQuery.from_dict({"columns": ["price"]})


def test_presets_compile_and_run() -> None:
    validate_presets()
    assert len({p["name"] for p in PRESETS}) == len(PRESETS)
    rows = _rows()
    by_name = {p["name"]: p for p in PRESETS}
    assert (
        apply_query(rows, ScanQuery.from_dict(by_name["Top gainers"]))[0][0]["symbol"] == "UPTREND"
    )
    assert apply_query(rows, ScanQuery.from_dict(by_name["Trending"]))[1] >= 0
    assert (
        apply_query(rows, ScanQuery.from_dict(by_name["Index futures"]))[0][0]["symbol"]
        == "NIFTYFUT"
    )
