import math
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from strategy.indicators import OUTPUTS, REGISTRY, compute, warmup

IST_OPEN = datetime(2026, 11, 16, 3, 45, tzinfo=UTC)  # 09:15 IST


def frame(closes: list[float], *, highs=None, lows=None, volumes=None, step_min=5) -> pl.DataFrame:
    n = len(closes)
    ts = [IST_OPEN + timedelta(minutes=step_min * i) for i in range(n)]
    highs = highs or [c + 1 for c in closes]
    lows = lows or [c - 1 for c in closes]
    return pl.DataFrame(
        {
            "ts": pl.Series(ts, dtype=pl.Datetime("us", "UTC")),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes or [100.0] * n,
            "oi": [None] * n,
        }
    )


def test_registry_outputs_match() -> None:
    for t, ind in REGISTRY.items():
        assert OUTPUTS[t] == ind.outputs
    assert warmup("RSI", {}) == 42 and warmup("EMA", {"period": 9}) == 27


def test_sma_and_ema_hand_computed() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    sma = compute("SMA", frame(closes), {"period": 3})["value"].to_list()
    assert sma[:2] == [None, None] and sma[2:] == [2.0, 3.0, 4.0, 5.0]
    ema = compute("EMA", frame(closes), {"period": 3})["value"].to_list()
    # seed = SMA(3) = 2.0 at index 2; k = 0.5
    expected = [None, None, 2.0, 3.0, 4.0, 5.0]
    for got, exp in zip(ema, expected, strict=True):
        if exp is None:
            assert got is None or math.isnan(got)
        else:
            assert got == pytest.approx(exp)


def test_rsi_wilder_hand_computed() -> None:
    closes = [10, 11, 12, 11, 10, 11, 12, 13, 12, 11, 12, 13, 14, 13, 12, 13]
    rsi = compute("RSI", frame([float(c) for c in closes]), {"period": 3})["value"].to_list()
    # manual Wilder RSI(3) at the first defined point (index 3): deltas +1,+1,-1
    # gains avg = (1+1+0)/3 = 0.6667, losses avg = (0+0+1)/3 = 0.3333 → RS=2 → RSI=66.67
    assert rsi[3] == pytest.approx(66.6667, abs=1e-3)
    # next step: delta -1 → gain avg = (0.6667*2+0)/3 = 0.4444, loss avg = (0.3333*2+1)/3 = 0.5556
    assert rsi[4] == pytest.approx(100 - 100 / (1 + 0.4444 / 0.5556), abs=1e-2)
    assert all(v is None or math.isnan(v) for v in rsi[:3])


def test_atr_wilder_hand_computed() -> None:
    closes = [10.0, 10.0, 10.0, 10.0, 10.0]
    highs = [11.0, 12.0, 11.0, 13.0, 11.0]
    lows = [9.0, 9.0, 9.0, 9.0, 9.0]
    atr = compute("ATR", frame(closes, highs=highs, lows=lows), {"period": 2})["value"].to_list()
    # TR: [2, 3, 2, 4, 2]; ATR(2) seed = mean(2,3)=2.5;
    # then (2.5+2)/2=2.25; (2.25+4)/2=3.125; (3.125+2)/2=2.5625
    assert atr[1] == pytest.approx(2.5)
    assert atr[2] == pytest.approx(2.25)
    assert atr[3] == pytest.approx(3.125)
    assert atr[4] == pytest.approx(2.5625)


def test_vwap_resets_per_session() -> None:
    closes = [10.0, 20.0]
    df = frame(closes, volumes=[100.0, 100.0], step_min=24 * 60)  # two different sessions
    out = compute("VWAP", df, {"anchor": "session"})
    assert out["value"].to_list() == [10.0, 20.0]  # no carry-over across sessions


def test_bollinger_and_volume_sma() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0]
    bb = compute("BOLLINGER", frame(closes), {"period": 3, "std": 1})
    assert bb["middle"].to_list()[2] == pytest.approx(2.0)
    sd = math.sqrt(2 / 3)
    assert bb["upper"].to_list()[2] == pytest.approx(2.0 + sd)
    vs = compute("VOLUME_SMA", frame(closes, volumes=[1.0, 2.0, 3.0, 4.0, 5.0]), {"period": 2})
    assert vs["value"].to_list()[1] == pytest.approx(1.5)


def test_opening_range_defined_after_window() -> None:
    closes = [float(x) for x in range(10)]
    df = frame(closes, step_min=5)
    out = compute("OPENING_RANGE", df, {"minutes": 15})
    assert out["high"][0] is None and out["high"][2] is None
    assert out["high"][3] == pytest.approx(3.0)  # max(high of first 3 bars) = 2+1
    assert out["low"][3] == pytest.approx(-1.0)


def test_swing_confirms_after_right_bars() -> None:
    highs = [1, 2, 5, 2, 1, 1, 1]
    lows = [0, 1, 4, 1, 0, 0, 0]
    df = frame(
        [float(h) - 0.5 for h in highs],
        highs=[float(h) for h in highs],
        lows=[float(lo) for lo in lows],
    )
    out = compute("SWING", df, {"left": 2, "right": 2})
    lh = out["last_high"].to_list()
    assert math.isnan(lh[3])
    assert lh[4] == 5.0 and lh[6] == 5.0


def test_macd_and_adx_shapes() -> None:
    closes = [float(100 + (i % 7) - 3 + i * 0.1) for i in range(120)]
    macd = compute("MACD", frame(closes), {"fast": 5, "slow": 10, "signal": 3})
    assert set(macd.columns) == {"macd", "signal", "hist"}
    assert macd["hist"].to_list()[-1] == pytest.approx(macd["macd"][-1] - macd["signal"][-1])
    adx = compute("ADX", frame(closes), {"period": 5})
    assert adx["value"].drop_nulls().drop_nans().len() > 50
    assert 0 <= adx["value"][-1] <= 100


def test_daily_trend_labels() -> None:
    closes = [float(100 + i) for i in range(200)]
    out = compute("DAILY_TREND", frame(closes, step_min=24 * 60), {"fast": 5, "slow": 10})
    assert out["label"][-1] == "up"
    down = compute("DAILY_TREND", frame(closes[::-1], step_min=24 * 60), {"fast": 5, "slow": 10})
    assert down["label"][-1] == "down"
