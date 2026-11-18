"""Indicator library v1 (spec §3). Each indicator computes over a Polars frame with columns
ts (UTC datetime), open, high, low, close, volume, oi (nullable) and returns a frame of its
output columns, row-aligned with the input. NaN/null means "not yet defined"; conditions on
null evaluate to false."""

from __future__ import annotations

from strategy.indicators.base import Indicator, IndicatorError
from strategy.indicators.library import (
    OUTPUTS,
    REGISTRY,
    compute,
    get,
    period_like_params,
    warmup,
)

__all__ = [
    "OUTPUTS",
    "REGISTRY",
    "Indicator",
    "IndicatorError",
    "compute",
    "get",
    "period_like_params",
    "warmup",
]
