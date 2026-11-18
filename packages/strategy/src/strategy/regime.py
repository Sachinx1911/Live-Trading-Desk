"""Market regime detection (master prompt Module 6). Deterministic, from daily candles and an
optional VIX series. Output feeds the DSL regime filters and the Phase 6 learning engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl

from core.models import Candle
from strategy.indicators.library import ADX, EMA

Trend = Literal["up", "down", "flat"]
Volatility = Literal["low", "normal", "high"]


@dataclass(frozen=True)
class Regime:
    trend: Trend
    volatility: Volatility
    adx: float | None
    vix: float | None
    label: str  # trending | sideways | bullish | bearish | high_vol | low_vol

    def as_dict(self) -> dict[str, float | str | None]:
        return {
            "daily_trend": self.trend,
            "volatility": self.volatility,
            "adx": self.adx,
            "vix": self.vix,
            "regime_label": self.label,
        }


class RegimeDetector:
    def __init__(
        self,
        fast: int = 20,
        slow: int = 50,
        adx_period: int = 14,
        adx_trending: float = 25.0,
        vix_low: float = 13.0,
        vix_high: float = 20.0,
    ) -> None:
        self.fast, self.slow, self.adx_period = fast, slow, adx_period
        self.adx_trending = adx_trending
        self.vix_low, self.vix_high = vix_low, vix_high

    def detect(self, daily: Sequence[Candle], vix: float | None = None) -> Regime:
        if len(daily) < self.slow + 3:
            return Regime("flat", "normal", None, vix, "sideways")
        df = pl.DataFrame(
            {
                "ts": [c.ts for c in daily],
                "open": [float(c.open) for c in daily],
                "high": [float(c.high) for c in daily],
                "low": [float(c.low) for c in daily],
                "close": [float(c.close) for c in daily],
                "volume": [float(c.volume) for c in daily],
                "oi": [None] * len(daily),
            }
        )
        fast = EMA().compute(df, period=self.fast)["value"]
        slow = EMA().compute(df, period=self.slow)["value"]
        adx_df = ADX().compute(df, period=self.adx_period)
        f, s, s3 = fast[-1], slow[-1], slow[-4]
        adx_v = adx_df["value"][-1]
        adx = None if adx_v is None or adx_v != adx_v else float(adx_v)
        trend: Trend = "flat"
        if f is not None and s is not None and s3 is not None:
            if f > s and s > s3:
                trend = "up"
            elif f < s and s < s3:
                trend = "down"
        vol: Volatility = "normal"
        if vix is not None:
            vol = "low" if vix < self.vix_low else "high" if vix > self.vix_high else "normal"
        else:
            closes = df["close"].to_numpy()
            rets = np.diff(closes) / closes[:-1]
            if len(rets) > 20:
                recent = float(np.std(rets[-20:]))
                longer = float(np.std(rets))
                vol = (
                    "high"
                    if recent > 1.3 * longer
                    else "low"
                    if recent < 0.7 * longer
                    else "normal"
                )
        if vol == "high":
            label = "high_vol"
        elif vol == "low" and trend == "flat":
            label = "low_vol"
        elif trend == "up":
            label = "bullish" if (adx is None or adx >= self.adx_trending) else "trending"
        elif trend == "down":
            label = "bearish"
        else:
            label = "trending" if (adx is not None and adx >= self.adx_trending) else "sideways"
        return Regime(trend, vol, adx, vix, label)
