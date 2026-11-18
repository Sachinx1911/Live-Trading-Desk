from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

import polars as pl

Params = Mapping[str, float | int | str]


class IndicatorError(ValueError):
    pass


class Indicator(ABC):
    type: str
    outputs: tuple[str, ...]
    period_params: tuple[str, ...] = ()
    defaults: dict[str, float | int | str] = {}

    def params(self, raw: Params) -> dict[str, float | int | str]:
        merged: dict[str, float | int | str] = {**self.defaults, **dict(raw)}
        for p in self.period_params:
            v = merged.get(p)
            if not isinstance(v, int | float) or v <= 0:
                raise IndicatorError(f"{self.type}: parameter '{p}' must be a positive number")
            merged[p] = int(v)
        return merged

    @abstractmethod
    def warmup(self, params: Params) -> int: ...

    @abstractmethod
    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame: ...
