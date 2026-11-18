from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from core.calendar import nse_calendar
from core.models import Candle, OrderSide, Timeframe
from strategy.dsl.examples import load_example
from strategy.dsl.schema import StrategyDocument
from strategy.engine import StrategyEngine

CAL = nse_calendar()
DAY_OPEN = datetime(2026, 11, 16, 3, 45, tzinfo=UTC)  # Monday 09:15 IST


BARS_PER_DAY = 74  # 09:15 .. 15:20 on 5-minute bars


def bar_ts(i: int, day_open: datetime = DAY_OPEN) -> datetime:
    """5-minute bars across consecutive weekdays, session-aligned."""
    day, j = divmod(i, BARS_PER_DAY)
    d = day_open
    while day > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            day -= 1
    return d + timedelta(minutes=5 * j)


def candle(i: int, close: float, *, day_open: datetime = DAY_OPEN, spread: float = 0.5) -> Candle:
    ts = bar_ts(i, day_open)
    return Candle(
        instrument_id=22,
        timeframe=Timeframe.M5,
        ts=ts,
        open=Decimal(str(close)),
        high=Decimal(str(close + spread)),
        low=Decimal(str(close - spread)),
        close=Decimal(str(close)),
        volume=100,
        provider_id="fake",
        received_at=ts,
    )


def series() -> list[float]:
    """Flat, then a clear rise (EMA9 crosses above EMA21 with RSI>55), then a fall."""
    flat = [100.0] * BARS_PER_DAY  # whole first session: warm-up
    up = [100.0 + i * 1.5 for i in range(1, 16)]
    hold = [up[-1]] * 3
    down = [up[-1] - i * 2.0 for i in range(1, 16)]
    return flat + up + hold + down


def make_engine(doc_raw=None, **kw) -> StrategyEngine:
    raw = doc_raw or load_example("ema_rsi_nifty")
    doc = StrategyDocument.model_validate(raw)
    return StrategyEngine(doc, 22, CAL, strategy_version_id=1, **kw)


def run(engine: StrategyEngine, closes: list[float], *, fill: bool = True) -> list:
    """Drive the engine; emulate a runner that fills entries/exits immediately."""
    out = []
    for i, c in enumerate(closes):
        for sig in engine.on_candle(candle(i, c)):
            out.append(sig)
            if fill:
                if sig.kind == "entry":
                    qty = 75 if sig.side == OrderSide.BUY else -75
                    engine.set_position(qty, sig.reference_price)
                elif (
                    sig.kind in ("exit", "stop", "target", "square_off")
                    and sig.reason != "trailing stop tightened"
                ):
                    engine.set_position(0, None)
    return out


def test_ema_cross_entry_then_exit_with_atr_levels() -> None:
    eng = make_engine()
    sigs = run(eng, series())
    kinds = [s.kind for s in sigs]
    assert kinds[0] == "entry" and sigs[0].side == OrderSide.BUY
    assert sigs[0].suggested_quantity == 1  # fixed_lots → lots
    assert sigs[0].stop_price is not None and sigs[0].target_price is not None
    entry = float(sigs[0].reference_price)
    atr = float(entry - float(sigs[0].stop_price))  # 1 ATR below
    assert atr > 0
    assert float(sigs[0].target_price) == pytest.approx(entry + 2 * atr, abs=0.02)
    # exactly one entry; it leaves the trade by rule, stop or target later
    assert kinds.count("entry") == 1
    assert any(k in ("exit", "stop", "target") for k in kinds[1:])


def test_no_entry_before_warmup_and_determinism() -> None:
    a = run(make_engine(), series())
    b = run(make_engine(), series())
    assert [(s.kind, s.ts, s.reference_price, s.stop_price) for s in a] == [
        (s.kind, s.ts, s.reference_price, s.stop_price) for s in b
    ]
    eng = make_engine()
    assert eng.on_candle(candle(0, 100.0)) == [] and not eng.state.warmed_up


def test_square_off_signal_at_1515_ist() -> None:
    eng = make_engine()
    run(eng, series()[:85], fill=False)
    eng.set_position(75, Decimal("110"))  # runner reports an open long
    assert eng.state.position == "long"
    last = bar_ts(84)
    before = last.replace(hour=9, minute=44)  # 15:14 IST on the same day
    at = last.replace(hour=9, minute=45)  # 15:15 IST
    assert eng.on_time(before) == []
    sigs = eng.on_time(at)
    assert len(sigs) == 1 and sigs[0].kind == "square_off" and sigs[0].side == OrderSide.SELL
    assert eng.on_time(at + timedelta(minutes=1)) == []  # only once per session


def test_no_entries_after_cutoff() -> None:
    eng = make_engine()
    sigs = []
    closes = series()
    # warm up on day 1, then present the cross after 14:45 IST on day 2
    for i, c in enumerate(closes[:BARS_PER_DAY]):
        sigs += eng.on_candle(candle(i, c))
    late = bar_ts(BARS_PER_DAY) + timedelta(minutes=5 * 67)  # 14:50 IST on day 2
    for i, c in enumerate(closes[BARS_PER_DAY:]):
        sigs += eng.on_candle(candle(i, c, day_open=late))
    assert all(s.kind != "entry" for s in sigs)
    assert "outside entry window" in eng.state.rejections


def test_cooldown_blocks_immediate_reentry() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["entry"]["cooldown_bars"] = 50
    raw["exit"] = {"time_exit_bars": 2}
    eng = make_engine(raw)
    closes = series() + [series()[-1] + i * 1.5 for i in range(1, 40)]  # second rise
    seen_cooldown = False
    entries = 0
    for i, c in enumerate(closes):
        for sig in eng.on_candle(candle(i, c)):
            if sig.kind == "entry":
                entries += 1
                eng.set_position(75, sig.reference_price)
            elif sig.kind in ("exit", "stop", "target"):
                eng.set_position(0, None)
        seen_cooldown = seen_cooldown or "cooldown" in eng.state.rejections
    assert entries == 1
    assert seen_cooldown


def test_max_trades_per_day() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["max_trades_per_day"] = 1
    raw["exit"] = {"time_exit_bars": 1}
    eng = make_engine(raw)
    closes = series() + [series()[-1] + i * 1.5 for i in range(1, 40)]
    sigs = run(eng, closes)
    assert [s.kind for s in sigs].count("entry") == 1


def test_time_exit_and_trailing_tightens_only() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["exit"] = {"time_exit_bars": 3}
    raw["trailing"] = {"mode": "points", "value": 1.0}
    eng = make_engine(raw, monitor_levels=False)
    sigs = run(eng, series())
    kinds = [s.kind for s in sigs]
    assert "entry" in kinds and "exit" in kinds
    stops = [float(s.stop_price) for s in sigs if s.reason == "trailing stop tightened"]
    assert stops == sorted(stops)  # never loosens for a long


def test_regime_filter_blocks_entry() -> None:
    raw = load_example("ema_rsi_nifty")
    raw["regime_filters"] = [{"source": "vix", "min": 10, "max": 12}]
    eng = make_engine(raw, regime_provider=lambda ts: {"vix": 25.0})
    sigs = run(eng, series())
    assert all(s.kind != "entry" for s in sigs)
    assert any("vix" in r for r in eng.state.rejections)
