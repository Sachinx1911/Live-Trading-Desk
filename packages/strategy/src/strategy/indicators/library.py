"""Indicator implementations. Recursive (Wilder/EMA) parts use NumPy loops; everything
else is Polars expressions. Deterministic and side-effect free."""

from __future__ import annotations

import math
from collections.abc import Mapping
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from strategy.indicators.base import Indicator, IndicatorError, Params

IST = ZoneInfo("Asia/Kolkata")


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    # seed with SMA of the first `period` values (TA-Lib convention)
    out[period - 1] = float(np.mean(values[:period]))
    for i in range(period, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def _wilder(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder smoothing: first value = mean of first `period`, then (prev*(n-1)+x)/n."""
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    out[period - 1] = float(np.mean(values[:period]))
    for i in range(period, len(values)):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def _true_range(df: pl.DataFrame) -> np.ndarray:
    h = df["high"].to_numpy().astype(float)
    lo = df["low"].to_numpy().astype(float)
    c = df["close"].to_numpy().astype(float)
    prev_c = np.roll(c, 1)
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev_c), np.abs(lo - prev_c)))
    if len(tr):
        tr[0] = h[0] - lo[0]
    return np.asarray(tr, dtype=float)


def _session_key(df: pl.DataFrame) -> pl.Series:
    return df["ts"].dt.convert_time_zone("Asia/Kolkata").dt.date().alias("_session")


class EMA(Indicator):
    type = "EMA"
    outputs = ("value",)
    period_params = ("period",)

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"]) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        src = str(p.get("source", "close"))
        return pl.DataFrame({"value": _ema(df[src].to_numpy().astype(float), int(p["period"]))})


class SMA(Indicator):
    type = "SMA"
    outputs = ("value",)
    period_params = ("period",)

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"])

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        src = str(p.get("source", "close"))
        return df.select(pl.col(src).rolling_mean(int(p["period"])).alias("value"))


class RSI(Indicator):
    type = "RSI"
    outputs = ("value",)
    period_params = ("period",)
    defaults = {"period": 14}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"]) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        n = int(p["period"])
        c = df[str(p.get("source", "close"))].to_numpy().astype(float)
        out = np.full(len(c), np.nan)
        if len(c) <= n:
            return pl.DataFrame({"value": out})
        delta = np.diff(c)
        gains = np.where(delta > 0, delta, 0.0)
        losses = np.where(delta < 0, -delta, 0.0)
        ag = _wilder(gains, n)
        al = _wilder(losses, n)
        for i in range(n - 1, len(delta)):
            if math.isnan(ag[i]):
                continue
            out[i + 1] = 100.0 if al[i] == 0 else 100.0 - 100.0 / (1.0 + ag[i] / al[i])
        return pl.DataFrame({"value": out})


class ATR(Indicator):
    type = "ATR"
    outputs = ("value",)
    period_params = ("period",)
    defaults = {"period": 14}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"]) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        return pl.DataFrame({"value": _wilder(_true_range(df), int(p["period"]))})


class VWAP(Indicator):
    type = "VWAP"
    outputs = ("value", "upper_1", "lower_1", "upper_2", "lower_2")
    defaults = {"anchor": "session"}

    def warmup(self, params: Params) -> int:
        return 1

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        tp = ((pl.col("high") + pl.col("low") + pl.col("close")) / 3).alias("_tp")
        vol = pl.col("volume").cast(pl.Float64).fill_null(0.0)
        d = df.with_columns(_session_key(df), tp).with_columns(
            (pl.col("_tp") * vol).cum_sum().over("_session").alias("_pv"),
            vol.cum_sum().over("_session").alias("_v"),
            (pl.col("_tp") ** 2 * vol).cum_sum().over("_session").alias("_pv2"),
        )
        value = pl.when(pl.col("_v") > 0).then(pl.col("_pv") / pl.col("_v")).otherwise(None)
        var = (
            pl.when(pl.col("_v") > 0)
            .then(pl.col("_pv2") / pl.col("_v") - (pl.col("_pv") / pl.col("_v")) ** 2)
            .otherwise(None)
        )
        sd = pl.when(var > 0).then(var.sqrt()).otherwise(0.0)
        return d.select(
            value.alias("value"),
            (value + sd).alias("upper_1"),
            (value - sd).alias("lower_1"),
            (value + 2 * sd).alias("upper_2"),
            (value - 2 * sd).alias("lower_2"),
        )


class SUPERTREND(Indicator):
    type = "SUPERTREND"
    outputs = ("value", "direction")
    period_params = ("period",)
    defaults = {"period": 10, "multiplier": 3}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"]) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        n, mult = int(p["period"]), float(p["multiplier"])
        atr = _wilder(_true_range(df), n)
        h = df["high"].to_numpy().astype(float)
        lo = df["low"].to_numpy().astype(float)
        c = df["close"].to_numpy().astype(float)
        hl2 = (h + lo) / 2
        upper = hl2 + mult * atr
        lower = hl2 - mult * atr
        value = np.full(len(c), np.nan)
        direction = np.full(len(c), np.nan)
        fu, fl = upper.copy(), lower.copy()
        for i in range(1, len(c)):
            if math.isnan(atr[i]) or math.isnan(atr[i - 1]):
                continue
            fu[i] = upper[i] if upper[i] < fu[i - 1] or c[i - 1] > fu[i - 1] else fu[i - 1]
            fl[i] = lower[i] if lower[i] > fl[i - 1] or c[i - 1] < fl[i - 1] else fl[i - 1]
            prev_dir = direction[i - 1] if not math.isnan(direction[i - 1]) else -1.0
            if prev_dir == -1.0:  # was in downtrend (value = upper band)
                direction[i] = 1.0 if c[i] > fu[i] else -1.0
            else:
                direction[i] = -1.0 if c[i] < fl[i] else 1.0
            value[i] = fl[i] if direction[i] == 1.0 else fu[i]
        return pl.DataFrame({"value": value, "direction": direction})


class BOLLINGER(Indicator):
    type = "BOLLINGER"
    outputs = ("upper", "middle", "lower", "width")
    period_params = ("period",)
    defaults = {"period": 20, "std": 2}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"])

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        n, k = int(p["period"]), float(p["std"])
        src = pl.col(str(p.get("source", "close")))
        mid = src.rolling_mean(n)
        sd = src.rolling_std(n, ddof=0)
        return df.select(
            (mid + k * sd).alias("upper"),
            mid.alias("middle"),
            (mid - k * sd).alias("lower"),
            ((2 * k * sd) / mid).alias("width"),
        )


class ADX(Indicator):
    type = "ADX"
    outputs = ("value", "plus_di", "minus_di")
    period_params = ("period",)
    defaults = {"period": 14}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"]) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        n = int(p["period"])
        h = df["high"].to_numpy().astype(float)
        lo = df["low"].to_numpy().astype(float)
        tr = _true_range(df)
        up = np.diff(h, prepend=h[0])
        down = -np.diff(lo, prepend=lo[0])
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        atr = _wilder(tr, n)
        pdm = _wilder(plus_dm, n)
        mdm = _wilder(minus_dm, n)
        with np.errstate(divide="ignore", invalid="ignore"):
            plus_di = 100 * pdm / atr
            minus_di = 100 * mdm / atr
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        dx = np.where(np.isnan(dx), np.nan, dx)
        adx = np.full(len(dx), np.nan)
        valid = np.where(~np.isnan(dx))[0]
        if len(valid) >= n:
            start = valid[0]
            seg = _wilder(dx[start:], n)
            adx[start:] = seg
        return pl.DataFrame({"value": adx, "plus_di": plus_di, "minus_di": minus_di})


class MACD(Indicator):
    type = "MACD"
    outputs = ("macd", "signal", "hist")
    period_params = ("fast", "slow", "signal")
    defaults = {"fast": 12, "slow": 26, "signal": 9}

    def warmup(self, params: Params) -> int:
        p = self.params(params)
        return (int(p["slow"]) + int(p["signal"])) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        c = df[str(p.get("source", "close"))].to_numpy().astype(float)
        macd = _ema(c, int(p["fast"])) - _ema(c, int(p["slow"]))
        valid = ~np.isnan(macd)
        sig = np.full(len(c), np.nan)
        if valid.any():
            first = int(np.argmax(valid))
            sig[first:] = _ema(macd[first:], int(p["signal"]))
        return pl.DataFrame({"macd": macd, "signal": sig, "hist": macd - sig})


class VOLUME_SMA(Indicator):  # noqa: N801 - matches the DSL type name
    type = "VOLUME_SMA"
    outputs = ("value",)
    period_params = ("period",)

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["period"])

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        return df.select(
            pl.col("volume").cast(pl.Float64).rolling_mean(int(p["period"])).alias("value")
        )


class PREV_DAY(Indicator):  # noqa: N801
    type = "PREV_DAY"
    outputs = ("high", "low", "close")

    def warmup(self, params: Params) -> int:
        return 1

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        d = df.with_columns(_session_key(df))
        daily = d.group_by("_session", maintain_order=True).agg(
            pl.col("high").max().alias("_dh"),
            pl.col("low").min().alias("_dl"),
            pl.col("close").last().alias("_dc"),
        )
        daily = daily.with_columns(
            pl.col("_dh").shift(1).alias("high"),
            pl.col("_dl").shift(1).alias("low"),
            pl.col("_dc").shift(1).alias("close"),
        ).select("_session", "high", "low", "close")
        return (
            d.select("_session")
            .join(daily, on="_session", how="left")
            .select("high", "low", "close")
        )


class OPENING_RANGE(Indicator):  # noqa: N801
    type = "OPENING_RANGE"
    outputs = ("high", "low")
    defaults = {"minutes": 15}

    def warmup(self, params: Params) -> int:
        return 1

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        minutes = int(p["minutes"])
        local = df["ts"].dt.convert_time_zone("Asia/Kolkata")
        d = df.with_columns(
            local.dt.date().alias("_session"),
            (local.dt.hour().cast(pl.Int32) * 60 + local.dt.minute().cast(pl.Int32)).alias("_min"),
        )
        open_min = 9 * 60 + 15
        in_range = pl.col("_min") < open_min + minutes
        d = d.with_columns(
            pl.when(in_range)
            .then(pl.col("high"))
            .otherwise(None)
            .max()
            .over("_session")
            .alias("_rh"),
            pl.when(in_range)
            .then(pl.col("low"))
            .otherwise(None)
            .min()
            .over("_session")
            .alias("_rl"),
        )
        # defined only once the range window has fully elapsed (bar open >= open+minutes)
        done = pl.col("_min") >= open_min + minutes
        return d.select(
            pl.when(done).then(pl.col("_rh")).otherwise(None).alias("high"),
            pl.when(done).then(pl.col("_rl")).otherwise(None).alias("low"),
        )


class OI_CHANGE(Indicator):  # noqa: N801
    type = "OI_CHANGE"
    outputs = ("value", "pct")
    period_params = ("lookback_bars",)
    defaults = {"lookback_bars": 1}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["lookback_bars"]) + 1

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        n = int(p["lookback_bars"])
        if "oi" not in df.columns:
            return pl.DataFrame({"value": [None] * len(df), "pct": [None] * len(df)})
        oi = pl.col("oi").cast(pl.Float64)
        prev = oi.shift(n)
        return df.select(
            (oi - prev).alias("value"),
            pl.when(prev > 0).then((oi - prev) / prev * 100).otherwise(None).alias("pct"),
        )


class SWING(Indicator):
    type = "SWING"
    outputs = ("last_high", "last_low")
    defaults = {"left": 5, "right": 5}

    def warmup(self, params: Params) -> int:
        p = self.params(params)
        return int(p["left"]) + int(p["right"]) + 1

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        left, right = int(p["left"]), int(p["right"])
        h = df["high"].to_numpy().astype(float)
        lo = df["low"].to_numpy().astype(float)
        n = len(h)
        last_high = np.full(n, np.nan)
        last_low = np.full(n, np.nan)
        cur_h, cur_l = np.nan, np.nan
        for i in range(n):
            # a swing at index j is confirmed at bar j + right
            j = i - right
            if j - left >= 0:
                win_h = h[j - left : j + right + 1]
                win_l = lo[j - left : j + right + 1]
                if h[j] == win_h.max():
                    cur_h = h[j]
                if lo[j] == win_l.min():
                    cur_l = lo[j]
            last_high[i] = cur_h
            last_low[i] = cur_l
        return pl.DataFrame({"last_high": last_high, "last_low": last_low})


class DAILY_TREND(Indicator):  # noqa: N801
    type = "DAILY_TREND"
    outputs = ("label",)
    period_params = ("fast", "slow")
    defaults = {"fast": 20, "slow": 50}

    def warmup(self, params: Params) -> int:
        return int(self.params(params)["slow"]) * 3

    def compute(self, df: pl.DataFrame, **params: float | int | str) -> pl.DataFrame:
        p = self.params(params)
        c = df["close"].to_numpy().astype(float)
        fast = _ema(c, int(p["fast"]))
        slow = _ema(c, int(p["slow"]))
        labels: list[str | None] = []
        for i in range(len(c)):
            if math.isnan(fast[i]) or math.isnan(slow[i]) or i < 3 or math.isnan(slow[i - 3]):
                labels.append(None)
            elif fast[i] > slow[i] and slow[i] > slow[i - 3]:
                labels.append("up")
            elif fast[i] < slow[i] and slow[i] < slow[i - 3]:
                labels.append("down")
            else:
                labels.append("sideways")
        return pl.DataFrame({"label": pl.Series(labels, dtype=pl.Utf8)})


REGISTRY: dict[str, Indicator] = {
    ind.type: ind
    for ind in (
        EMA(),
        SMA(),
        RSI(),
        ATR(),
        VWAP(),
        SUPERTREND(),
        BOLLINGER(),
        ADX(),
        MACD(),
        VOLUME_SMA(),
        PREV_DAY(),
        OPENING_RANGE(),
        OI_CHANGE(),
        SWING(),
        DAILY_TREND(),
    )
}
OUTPUTS: dict[str, tuple[str, ...]] = {k: v.outputs for k, v in REGISTRY.items()}


def get(type_: str) -> Indicator:
    try:
        return REGISTRY[type_]
    except KeyError as exc:
        raise IndicatorError(f"unknown indicator type {type_!r}") from exc


def compute(type_: str, df: pl.DataFrame, params: Mapping[str, float | int | str]) -> pl.DataFrame:
    return get(type_).compute(df, **params)


def warmup(type_: str, params: Mapping[str, float | int | str]) -> int:
    return get(type_).warmup(params)


def period_like_params(type_: str, params: Mapping[str, float | int | str]) -> list[int]:
    ind = get(type_)
    merged = ind.params(params) if ind.period_params else {**ind.defaults, **dict(params)}
    out: list[int] = []
    for name in ind.period_params:
        v = merged.get(name)
        if isinstance(v, int | float):
            out.append(int(v))
    for name in ("minutes", "left", "right"):
        v = merged.get(name)
        if isinstance(v, int | float) and name in ind.defaults:
            out.append(int(v))
    return out
