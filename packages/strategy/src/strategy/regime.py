"""Market regime detection (master prompt Module 6). Deterministic, from daily candles, an
optional VIX series and the events calendar. No LLM anywhere in here.

Two outputs:
- `RegimeDaily`  — computed once per session from daily bars (trend, strength, volatility,
  structure, numbers, event flag). Stored in `regime_daily`.
- `RegimeIntraday` — day type from today's intraday bars after 09:45 IST (opening range,
  VWAP distance). Stored in `regime_intraday`.

`as_dict()` of both also carries the keys the strategy engine's regime filters read
(`daily_trend`, `regime_label`, `vix`, `volatility`, `day_type`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

import numpy as np
import polars as pl

from core.models import Candle
from core.time import IST, ensure_utc
from strategy.indicators.library import ADX, ATR, EMA

Trend = Literal["up", "down", "flat"]
Volatility = Literal["low", "normal", "high"]
TrendState = Literal["up", "down", "sideways"]
Strength = Literal["weak", "moderate", "strong"]
Structure = Literal["bullish", "bearish", "range"]
DayType = Literal["trending", "range", "volatile_open", "unknown"]


# ----------------------------------------------------------------------------- legacy (Phase 3)
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


# ----------------------------------------------------------------------------- new (Phase 4+)
@dataclass(frozen=True)
class RegimeDaily:
    date: date
    trend: TrendState
    strength: Strength
    volatility: Volatility
    structure: Structure
    adx: float | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    atr_pct: float | None
    vix: float | None
    vix_percentile: float | None
    event_day: bool
    events: list[str] = field(default_factory=list)
    computed_at: datetime | None = None

    @property
    def label(self) -> str:
        """Single word for dashboards and the legacy `regime_label` filter."""
        if self.volatility == "high":
            return "high_vol"
        if self.trend == "up":
            return "bullish"
        if self.trend == "down":
            return "bearish"
        return "low_vol" if self.volatility == "low" else "sideways"

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "trend": self.trend,
            "strength": self.strength,
            "volatility": self.volatility,
            "structure": self.structure,
            "adx": self.adx,
            "ema20": self.ema20,
            "ema50": self.ema50,
            "ema200": self.ema200,
            "atr_pct": self.atr_pct,
            "vix": self.vix,
            "vix_percentile": self.vix_percentile,
            "event_day": self.event_day,
            "events": list(self.events),
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            # keys read by StrategyEngine._regime_ok
            "daily_trend": "flat" if self.trend == "sideways" else self.trend,
            "regime_label": self.label,
        }


@dataclass(frozen=True)
class RegimeIntraday:
    ts: datetime
    day_type: DayType
    or_high: float | None
    or_low: float | None
    vwap_distance_pct: float | None
    atr_ratio: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "day_type": self.day_type,
            "or_high": self.or_high,
            "or_low": self.or_low,
            "vwap_distance_pct": self.vwap_distance_pct,
            "atr_ratio": self.atr_ratio,
        }


def _frame(candles: Sequence[Candle]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [ensure_utc(c.ts) for c in candles],
            "open": [float(c.open) for c in candles],
            "high": [float(c.high) for c in candles],
            "low": [float(c.low) for c in candles],
            "close": [float(c.close) for c in candles],
            "volume": [float(c.volume) for c in candles],
            "oi": [None] * len(candles),
        }
    )


def _last(series: pl.Series) -> float | None:
    if len(series) == 0:
        return None
    v = series[-1]
    if v is None:
        return None
    f = float(v)
    return None if f != f else f


def _percentile(values: np.ndarray, x: float) -> float:
    """Percent of values strictly below x (0-100)."""
    if values.size == 0:
        return 50.0
    return float((values < x).sum()) / float(values.size) * 100.0


def _swings(high: np.ndarray, low: np.ndarray, k: int = 5) -> tuple[list[float], list[float]]:
    """Confirmed swing highs/lows: the bar is the extreme of a (2k+1)-bar window."""
    hs: list[float] = []
    ls: list[float] = []
    n = len(high)
    for i in range(k, n - k):
        win_h = high[i - k : i + k + 1]
        win_l = low[i - k : i + k + 1]
        if high[i] >= win_h.max() and (win_h == high[i]).sum() == 1:
            hs.append(float(high[i]))
        if low[i] <= win_l.min() and (win_l == low[i]).sum() == 1:
            ls.append(float(low[i]))
    return hs, ls


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

    # ------------------------------------------------------------------ legacy API (kept)
    def detect(self, daily: Sequence[Candle], vix: float | None = None) -> Regime:
        if len(daily) < self.slow + 3:
            return Regime("flat", "normal", None, vix, "sideways")
        df = _frame(daily)
        fast = EMA().compute(df, period=self.fast)["value"]
        slow = EMA().compute(df, period=self.slow)["value"]
        adx_df = ADX().compute(df, period=self.adx_period)
        f, s, s3 = fast[-1], slow[-1], slow[-4]
        adx = _last(adx_df["value"])
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

    # ------------------------------------------------------------------ daily regime
    def daily(
        self,
        daily_candles: Sequence[Candle],
        vix_daily: Sequence[Candle] | None = None,
        events_today: Sequence[str] = (),
        *,
        computed_at: datetime | None = None,
    ) -> RegimeDaily:
        """Regime for the session of the LAST candle in `daily_candles`.

        Trend: EMA20/50/200 ordering plus close vs EMA20; ADX(14) < 20 forces `sideways`.
        Strength: ADX bands weak (<20) / moderate (20-30) / strong (>30).
        Volatility: VIX 1-year percentile (<25 low, >75 high) when a VIX series is given,
        else ATR(14)/close percentile over the series. Structure: last two confirmed swing
        highs and lows (5-bar swings): HH+HL bullish, LH+LL bearish, else range.
        """
        if not daily_candles:
            raise ValueError("daily_candles must not be empty")
        cs = sorted(daily_candles, key=lambda c: c.ts)
        day = ensure_utc(cs[-1].ts).astimezone(IST).date()
        df = _frame(cs)
        n = len(cs)
        close = df["close"].to_numpy()

        ema20 = _last(EMA().compute(df, period=20)["value"]) if n >= 20 else None
        ema50 = _last(EMA().compute(df, period=50)["value"]) if n >= 50 else None
        ema200 = _last(EMA().compute(df, period=200)["value"]) if n >= 200 else None
        adx = (
            _last(ADX().compute(df, period=self.adx_period)["value"])
            if n >= 2 * self.adx_period
            else None
        )
        atr = _last(ATR().compute(df, period=14)["value"]) if n >= 15 else None
        last_close = float(close[-1])
        atr_pct = (atr / last_close * 100.0) if atr and last_close else None

        # --- trend --------------------------------------------------------------------
        # Trend is the tradeable (weeks-scale) direction: close vs EMA20 vs EMA50 with ADX
        # confirming. EMA200 is reported for context but does not gate the label; otherwise a
        # strong rally off a long decline reads as "sideways/strong", which is contradictory.
        trend: TrendState = "sideways"
        if ema20 is not None and ema50 is not None:
            if last_close > ema20 > ema50:
                trend = "up"
            elif last_close < ema20 < ema50:
                trend = "down"
        if adx is not None and adx < 20:
            trend = "sideways"
        strength: Strength = (
            "weak" if adx is None or adx < 20 else "moderate" if adx <= 30 else "strong"
        )

        # --- volatility ---------------------------------------------------------------
        vix: float | None = None
        vix_pct: float | None = None
        vol: Volatility
        if vix_daily:
            vs = sorted(vix_daily, key=lambda c: c.ts)
            vs = [c for c in vs if ensure_utc(c.ts).astimezone(IST).date() <= day]
            if vs:
                vix = float(vs[-1].close)
                window = np.array([float(c.close) for c in vs[-252:]], dtype=float)
                vix_pct = _percentile(window, vix)
        if vix_pct is not None:
            vol = "low" if vix_pct < 25 else "high" if vix_pct > 75 else "normal"
        elif atr_pct is not None and n >= 30:
            atr_series = ATR().compute(df, period=14)["value"].to_numpy()
            pct_series = (atr_series / close) * 100.0
            pct_series = pct_series[~np.isnan(pct_series)][-252:]
            p = _percentile(pct_series, atr_pct)
            vol = "low" if p < 25 else "high" if p > 75 else "normal"
        else:
            vol = "normal"

        # --- structure ----------------------------------------------------------------
        structure: Structure = "range"
        highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
        hs, ls = _swings(highs, lows)
        if len(hs) < 2 or len(ls) < 2:
            # Persistent one-way moves never confirm a pivot inside the window; fall back to
            # comparing the last two 20-bar blocks (higher high + higher low, etc.).
            if len(highs) >= 40:
                hs = [float(highs[-40:-20].max()), float(highs[-20:].max())]
                ls = [float(lows[-40:-20].min()), float(lows[-20:].min())]
        if len(hs) >= 2 and len(ls) >= 2:
            if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
                structure = "bullish"
            elif hs[-1] < hs[-2] and ls[-1] < ls[-2]:
                structure = "bearish"

        return RegimeDaily(
            date=day,
            trend=trend,
            strength=strength,
            volatility=vol,
            structure=structure,
            adx=None if adx is None else round(adx, 2),
            ema20=None if ema20 is None else round(ema20, 2),
            ema50=None if ema50 is None else round(ema50, 2),
            ema200=None if ema200 is None else round(ema200, 2),
            atr_pct=None if atr_pct is None else round(atr_pct, 3),
            vix=None if vix is None else round(vix, 2),
            vix_percentile=None if vix_pct is None else round(vix_pct, 1),
            event_day=bool(events_today),
            events=list(events_today),
            computed_at=computed_at,
        )

    # ------------------------------------------------------------------ intraday day type
    def intraday(
        self,
        candles_today: Sequence[Candle],
        daily: RegimeDaily | None,
        now: datetime,
        *,
        or_end: time = time(9, 45),
        avg_30m_range: float | None = None,
    ) -> RegimeIntraday:
        """Day type after 09:45 IST from today's 1m/5m bars.

        trending: price left the opening range by > 0.5 x ATR(daily) and the VWAP distance has
        kept its sign for the last 30 minutes; range: price stayed within OR ± 0.3 x ATR;
        volatile_open: first-30-minute range > 1.2 x the average 30-minute range (when known);
        else unknown. ATR(daily) is derived from `daily.atr_pct x last close`.
        """
        now = ensure_utc(now)
        local_now = now.astimezone(IST)
        cs = sorted((c for c in candles_today if ensure_utc(c.ts) <= now), key=lambda c: c.ts)
        if not cs or local_now.time() < or_end:
            return RegimeIntraday(now, "unknown", None, None, None, None)
        session_open = datetime.combine(local_now.date(), time(9, 15), tzinfo=IST)
        or_cut = datetime.combine(local_now.date(), or_end, tzinfo=IST)
        opening = [c for c in cs if session_open <= ensure_utc(c.ts).astimezone(IST) < or_cut]
        if not opening:
            return RegimeIntraday(now, "unknown", None, None, None, None)
        or_high = max(float(c.high) for c in opening)
        or_low = min(float(c.low) for c in opening)
        last_close = float(cs[-1].close)
        atr_abs = (daily.atr_pct / 100.0 * last_close) if daily and daily.atr_pct else None

        # VWAP over the session so far (typical price x volume; falls back to close when
        # the instrument has no volume, e.g. indices)
        tp = np.array([(float(c.high) + float(c.low) + float(c.close)) / 3 for c in cs])
        vol = np.array([float(c.volume) for c in cs])
        cum_vol = np.cumsum(vol)
        if cum_vol[-1] > 0:
            vwap_series = np.cumsum(tp * vol) / np.where(cum_vol == 0, np.nan, cum_vol)
        else:
            vwap_series = np.cumsum(tp) / np.arange(1, len(tp) + 1)
        closes = np.array([float(c.close) for c in cs])
        dist = (closes - vwap_series) / vwap_series * 100.0
        vwap_distance_pct = float(dist[-1]) if dist.size and not np.isnan(dist[-1]) else None

        first_30 = [
            c
            for c in cs
            if session_open
            <= ensure_utc(c.ts).astimezone(IST)
            < session_open + timedelta(minutes=30)
        ]
        first_range = (
            max(float(c.high) for c in first_30) - min(float(c.low) for c in first_30)
            if first_30
            else None
        )
        atr_ratio = (first_range / atr_abs) if first_range is not None and atr_abs else None

        day_type: DayType = "unknown"
        if avg_30m_range and first_range is not None and first_range > 1.2 * avg_30m_range:
            day_type = "volatile_open"
        elif atr_abs:
            thirty = [ensure_utc(c.ts) >= now - timedelta(minutes=30) for c in cs]
            recent = dist[np.array(thirty)] if any(thirty) else dist[-1:]
            recent = recent[~np.isnan(recent)]
            same_sign = recent.size > 0 and (np.all(recent > 0) or np.all(recent < 0))
            left_or = last_close > or_high + 0.5 * atr_abs or last_close < or_low - 0.5 * atr_abs
            inside = or_low - 0.3 * atr_abs <= last_close <= or_high + 0.3 * atr_abs
            if left_or and same_sign:
                day_type = "trending"
            elif inside:
                day_type = "range"
        return RegimeIntraday(
            ts=now,
            day_type=day_type,
            or_high=round(or_high, 2),
            or_low=round(or_low, 2),
            vwap_distance_pct=None if vwap_distance_pct is None else round(vwap_distance_pct, 3),
            atr_ratio=None if atr_ratio is None else round(atr_ratio, 3),
        )


def provider_from_regimes(
    daily_by_date: dict[date, RegimeDaily],
    intraday_by_date: dict[date, RegimeIntraday] | None = None,
) -> Any:
    """Build a `regime_provider(ts) -> dict` for StrategyEngine from stored regimes.
    The regime used for a timestamp is the latest one computed for a date <= that day."""
    keys = sorted(daily_by_date)

    def provider(ts: datetime) -> dict[str, Any]:
        d = ensure_utc(ts).astimezone(IST).date()
        chosen: RegimeDaily | None = None
        for k in keys:
            if k <= d:
                chosen = daily_by_date[k]
            else:
                break
        out: dict[str, Any] = {}
        if chosen is not None:
            out = chosen.as_dict()
        intra = (intraday_by_date or {}).get(d)
        out["day_type"] = intra.day_type if intra else None
        return out

    return provider


def regime_table(trades: Sequence[Any], regime_of: Any) -> list[dict[str, Any]]:
    """Aggregate closed trades per (trend, volatility) and per day_type.

    `regime_of(trade) -> dict | None` returns the regime dict tagged at entry. Rows carry
    trades / wins / net_pnl / avg_pnl and are sorted deterministically.
    """
    buckets: dict[tuple[str, str], list[Decimal]] = {}
    for t in trades:
        r = regime_of(t) or {}
        keys = [
            ("trend_vol", f"{r.get('trend', 'unknown')}/{r.get('volatility', 'unknown')}"),
            ("day_type", str(r.get("day_type") or "unknown")),
        ]
        for kind, key in keys:
            buckets.setdefault((kind, key), []).append(Decimal(str(t.net_pnl)))
    rows: list[dict[str, Any]] = []
    for (kind, key), pnls in sorted(buckets.items()):
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        net = sum(pnls, Decimal(0))
        rows.append(
            {
                "kind": kind,
                "key": key,
                "trades": n,
                "wins": wins,
                "win_rate_pct": round(wins / n * 100.0, 2) if n else None,
                "net_pnl": float(net),
                "avg_pnl": float(net / n) if n else None,
            }
        )
    return rows
