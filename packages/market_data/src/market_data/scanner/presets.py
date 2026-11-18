"""Preset scans (TradingView screener presets adapted to NSE)."""

from __future__ import annotations

from typing import Any

from market_data.scanner.filters import DEFAULT_COLUMNS, FIELDS, ScanQuery

_EQ = {"field": "segment", "op": "eq", "value": "equity"}


def _p(
    name: str,
    description: str,
    all_: list[dict[str, Any]],
    sort: dict[str, str],
    columns: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "filters": {"all": all_, "any": []},
        "sort": sort,
        "columns": columns or DEFAULT_COLUMNS,
    }


PRESETS: list[dict[str, Any]] = [
    _p(
        "All stocks",
        "Every NSE equity with enough history",
        [_EQ],
        {"field": "volume", "dir": "desc"},
    ),
    _p(
        "Top gainers",
        "Biggest 1-day gains",
        [_EQ, {"field": "change_1d_pct", "op": "gt", "value": 0}],
        {"field": "change_1d_pct", "dir": "desc"},
    ),
    _p(
        "Top losers",
        "Biggest 1-day losses",
        [_EQ, {"field": "change_1d_pct", "op": "lt", "value": 0}],
        {"field": "change_1d_pct", "dir": "asc"},
    ),
    _p(
        "Volume shockers",
        "Volume at least 2x the 20-day average",
        [_EQ, {"field": "rel_volume", "op": "gte", "value": 2}],
        {"field": "rel_volume", "dir": "desc"},
        [
            "symbol",
            "name",
            "last_close",
            "change_1d_pct",
            "volume",
            "avg_volume_20",
            "rel_volume",
            "rsi14",
        ],
    ),
    _p(
        "52-week high breakouts",
        "Within 1% of the 52-week high",
        [_EQ, {"field": "dist_52w_high_pct", "op": "gte", "value": -1}],
        {"field": "dist_52w_high_pct", "dir": "desc"},
        [
            "symbol",
            "name",
            "last_close",
            "change_1d_pct",
            "dist_52w_high_pct",
            "rel_volume",
            "adx14",
        ],
    ),
    _p(
        "52-week low",
        "Within 1% of the 52-week low",
        [_EQ, {"field": "dist_52w_low_pct", "op": "lte", "value": 1}],
        {"field": "dist_52w_low_pct", "dir": "asc"},
        [
            "symbol",
            "name",
            "last_close",
            "change_1d_pct",
            "dist_52w_low_pct",
            "rel_volume",
            "rsi14",
        ],
    ),
    _p(
        "Trending",
        "ADX >= 25 with bullish EMA alignment (20 > 50 > 200)",
        [
            _EQ,
            {"field": "adx14", "op": "gte", "value": 25},
            {"field": "ema_alignment", "op": "eq", "value": "bull"},
        ],
        {"field": "adx14", "dir": "desc"},
        [
            "symbol",
            "name",
            "last_close",
            "change_20d_pct",
            "adx14",
            "ema20",
            "ema50",
            "ema200",
            "regime_trend",
        ],
    ),
    _p(
        "Oversold",
        "RSI 14 below 30",
        [_EQ, {"field": "rsi14", "op": "lt", "value": 30}],
        {"field": "rsi14", "dir": "asc"},
    ),
    _p(
        "Overbought",
        "RSI 14 above 70",
        [_EQ, {"field": "rsi14", "op": "gt", "value": 70}],
        {"field": "rsi14", "dir": "desc"},
    ),
    _p(
        "Low volatility",
        "ATR 14 under 1.5% of price",
        [_EQ, {"field": "atr14_pct", "op": "lt", "value": 1.5}],
        {"field": "atr14_pct", "dir": "asc"},
    ),
    _p(
        "High volatility",
        "ATR 14 above 3% of price",
        [_EQ, {"field": "atr14_pct", "op": "gt", "value": 3}],
        {"field": "atr14_pct", "dir": "desc"},
    ),
    _p(
        "Gap up",
        "Opened at least 1% above the previous close",
        [_EQ, {"field": "gap_pct", "op": "gte", "value": 1}],
        {"field": "gap_pct", "dir": "desc"},
        ["symbol", "name", "last_close", "gap_pct", "change_1d_pct", "rel_volume"],
    ),
    _p(
        "Gap down",
        "Opened at least 1% below the previous close",
        [_EQ, {"field": "gap_pct", "op": "lte", "value": -1}],
        {"field": "gap_pct", "dir": "asc"},
        ["symbol", "name", "last_close", "gap_pct", "change_1d_pct", "rel_volume"],
    ),
    _p(
        "Index futures",
        "NIFTY / BANKNIFTY futures with open interest",
        [{"field": "segment", "op": "eq", "value": "futures"}],
        {"field": "oi", "dir": "desc"},
        [
            "symbol",
            "underlying",
            "expiry",
            "last_close",
            "change_1d_pct",
            "oi",
            "oi_change_1d_pct",
            "volume",
        ],
    ),
]


def validate_presets() -> None:
    """Every preset must compile against the catalogue (tested)."""
    for p in PRESETS:
        ScanQuery.from_dict(p)
        for c in p["columns"]:
            assert c in FIELDS, c
