"""Regime detector: every label on synthetic series, plus provider/table helpers."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from core.calendar import nse_calendar
from core.models import Candle, Timeframe
from core.time import IST
from strategy.regime import (
    RegimeDaily,
    RegimeDetector,
    provider_from_regimes,
    regime_table,
)

CAL = nse_calendar()


def _trading_days(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if CAL.is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def _daily(
    closes: list[float], start: date = date(2025, 1, 1), spread: float = 0.01
) -> list[Candle]:
    days = _trading_days(start, len(closes))
    out = []
    for d, c in zip(days, closes, strict=True):
        ts = datetime.combine(d, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
        o = c * (1 - spread / 4)
        out.append(
            Candle(
                instrument_id=1,
                timeframe=Timeframe.D1,
                ts=ts,
                open=Decimal(f"{o:.2f}"),
                high=Decimal(f"{max(o, c) * (1 + spread):.2f}"),
                low=Decimal(f"{min(o, c) * (1 - spread):.2f}"),
                close=Decimal(f"{c:.2f}"),
                volume=1000,
                provider_id="test",
                received_at=ts,
            )
        )
    return out


def _vix(values: list[float], start: date = date(2025, 1, 1)) -> list[Candle]:
    return _daily(values, start, spread=0.0)


# A flat VIX history whose last value sits mid-range: volatility reads "normal", so the
# trend/structure tests below are not masked by the ATR fallback.
NORMAL_VIX = [14.0, 15.0, 16.0] * 86 + [15.0, 15.0]


def test_uptrend_strong_bullish_structure() -> None:
    closes = [100 + i * 1.2 + math.sin(i / 3) for i in range(260)]
    r = RegimeDetector().daily(_daily(closes), _vix(NORMAL_VIX))
    assert r.trend == "up" and r.strength in ("moderate", "strong")
    assert r.structure == "bullish"
    assert r.label == "bullish"
    assert r.ema20 is not None and r.ema50 is not None and r.ema200 is not None
    assert r.adx is not None and r.adx >= 20


def test_downtrend_bearish_structure() -> None:
    closes = [400 - i * 1.1 + math.sin(i / 3) for i in range(260)]
    r = RegimeDetector().daily(_daily(closes), _vix(NORMAL_VIX))
    assert r.trend == "down" and r.structure == "bearish" and r.label == "bearish"


def test_sideways_when_adx_low() -> None:
    closes = [200 + 2 * math.sin(i / 2.5) for i in range(260)]
    r = RegimeDetector().daily(_daily(closes))
    assert r.trend == "sideways" and r.strength == "weak"
    assert r.structure == "range"


def test_volatility_from_vix_percentile() -> None:
    closes = [100 + i * 0.5 for i in range(260)]
    low_vix = [20.0] * 250 + [10.0] * 10  # today's VIX at the bottom of the year
    high_vix = [12.0] * 250 + [30.0] * 10
    det = RegimeDetector()
    assert det.daily(_daily(closes), _vix(low_vix)).volatility == "low"
    assert det.daily(_daily(closes), _vix(high_vix)).volatility == "high"
    r = det.daily(_daily(closes), _vix(high_vix))
    assert r.vix == 30.0 and r.vix_percentile is not None and r.vix_percentile > 75
    assert r.label == "high_vol"


def test_volatility_from_atr_when_no_vix() -> None:
    calm = [100 + i * 0.3 for i in range(230)]
    wild = [calm[-1] * (1 + (0.08 if i % 2 else -0.07)) ** (i % 3) for i in range(30)]
    r = RegimeDetector().daily(_daily(calm + wild))
    assert r.vix is None and r.volatility == "high"


def test_event_day_and_as_dict_keys() -> None:
    r = RegimeDetector().daily(_daily([100 + i for i in range(60)]), events_today=["expiry: NIFTY"])
    d = r.as_dict()
    assert r.event_day and d["events"] == ["expiry: NIFTY"]
    for k in ("trend", "strength", "volatility", "structure", "daily_trend", "regime_label", "vix"):
        assert k in d
    assert d["daily_trend"] in ("up", "down", "flat")


def _intraday(day: date, path: list[float], start_minute: int = 0) -> list[Candle]:
    out = []
    base = datetime.combine(day, datetime.min.time(), tzinfo=IST).replace(hour=9, minute=15)
    for i, px in enumerate(path):
        ts = base + timedelta(minutes=start_minute + i)
        out.append(
            Candle(
                instrument_id=1,
                timeframe=Timeframe.M1,
                ts=ts,
                open=Decimal(f"{px:.2f}"),
                high=Decimal(f"{px + 0.5:.2f}"),
                low=Decimal(f"{px - 0.5:.2f}"),
                close=Decimal(f"{px:.2f}"),
                volume=100,
                provider_id="test",
                received_at=ts,
            )
        )
    return out


def _daily_regime(atr_pct: float) -> RegimeDaily:
    return RegimeDaily(
        date=date(2026, 11, 17),
        trend="up",
        strength="moderate",
        volatility="normal",
        structure="bullish",
        adx=25.0,
        ema20=1.0,
        ema50=1.0,
        ema200=1.0,
        atr_pct=atr_pct,
        vix=None,
        vix_percentile=None,
        event_day=False,
    )


def test_intraday_trending_day() -> None:
    day = date(2026, 11, 18)
    # flat opening range, then a steady climb far above OR + 0.5 ATR
    path = [1000.0] * 30 + [1000 + i * 1.5 for i in range(90)]
    cs = _intraday(day, path)
    now = cs[-1].ts
    r = RegimeDetector().intraday(cs, _daily_regime(atr_pct=1.0), now)  # ATR = 10 pts
    assert r.day_type == "trending"
    assert r.or_high is not None and r.or_low is not None and r.or_high >= 1000
    assert r.vwap_distance_pct is not None and r.vwap_distance_pct > 0


def test_intraday_range_day_and_before_cutoff() -> None:
    day = date(2026, 11, 18)
    path = [1000 + (1 if i % 2 else -1) * 0.4 for i in range(120)]
    cs = _intraday(day, path)
    det = RegimeDetector()
    assert det.intraday(cs, _daily_regime(1.0), cs[-1].ts).day_type == "range"
    early = det.intraday(cs[:20], _daily_regime(1.0), cs[19].ts)
    assert early.day_type == "unknown" and early.or_high is None


def test_intraday_volatile_open() -> None:
    day = date(2026, 11, 18)
    path = [1000 + (30 if i % 2 else -30) for i in range(30)] + [1000.0] * 60
    cs = _intraday(day, path)
    r = RegimeDetector().intraday(cs, _daily_regime(1.0), cs[-1].ts, avg_30m_range=20.0)
    assert r.day_type == "volatile_open" and r.atr_ratio is not None and r.atr_ratio > 1


def test_provider_and_regime_table() -> None:
    r1 = _daily_regime(1.0)
    r2 = RegimeDaily(
        **{**r1.__dict__, "date": date(2026, 11, 18), "trend": "down", "volatility": "high"}
    )
    prov = provider_from_regimes({r1.date: r1, r2.date: r2})
    ts17 = datetime(2026, 11, 17, 10, 0, tzinfo=IST)
    ts18 = datetime(2026, 11, 18, 10, 0, tzinfo=IST)
    assert prov(ts17)["trend"] == "up" and prov(ts18)["trend"] == "down"
    assert prov(datetime(2026, 11, 16, 10, 0, tzinfo=IST)) == {"day_type": None}

    class T:
        def __init__(self, pnl: float, regime: dict[str, str] | None) -> None:
            self.net_pnl = pnl
            self.regime = regime

    trades = [
        T(10, {"trend": "up", "volatility": "low", "day_type": "trending"}),
        T(-5, {"trend": "up", "volatility": "low"}),
        T(3, None),
    ]
    rows = regime_table(trades, lambda t: t.regime)
    tv = next(r for r in rows if r["kind"] == "trend_vol" and r["key"] == "up/low")
    assert (
        tv["trades"] == 2
        and tv["wins"] == 1
        and tv["net_pnl"] == 5.0
        and tv["win_rate_pct"] == 50.0
    )
    assert any(r["kind"] == "day_type" and r["key"] == "unknown" for r in rows)


def test_legacy_detect_still_works() -> None:
    closes = [100 + i for i in range(80)]
    r = RegimeDetector().detect(_daily(closes), vix=11.0)
    assert r.trend == "up" and r.volatility == "low" and r.as_dict()["daily_trend"] == "up"
