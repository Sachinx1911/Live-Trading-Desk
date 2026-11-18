from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from _synth import CAL, linear_sessions, make_candle, minimal_dsl, session_open_utc, trading_days

from backtest.config import SlippageConfig
from backtest.data import DataOrderError, HistoricalFeed
from backtest.metrics import compute_metrics
from backtest.report import render_report
from backtest.runner import run_backtest
from core.models import Timeframe


def test_determinism_same_seed(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    cfg = make_cfg(
        minimal_dsl(), three_sessions, slippage=SlippageConfig(model="spread_aware", bps=2)
    )
    a = run_backtest(cfg, three_sessions)
    b = run_backtest(cfg, three_sessions)
    assert a.config_hash == b.config_hash
    assert a.data_hash == b.data_hash
    assert [t.as_dict() for t in a.trades] == [t.as_dict() for t in b.trades]
    assert a.equity_curve == b.equity_curve
    assert render_report(a) == render_report(b)


def test_seed_changes_only_slippage(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    base = make_cfg(
        minimal_dsl(), three_sessions, slippage=SlippageConfig(model="spread_aware", bps=2)
    )
    a = run_backtest(base, three_sessions)
    b = run_backtest(base.model_copy(update={"seed": 99}), three_sessions)
    assert a.config_hash != b.config_hash
    assert len(a.trades) == len(b.trades)
    for ta, tb in zip(a.trades, b.trades, strict=True):
        assert (
            ta.entry_at == tb.entry_at and ta.exit_at == tb.exit_at and ta.quantity == tb.quantity
        )
    # fixed-bps slippage has no stochastic part: identical fills regardless of seed
    fixed = make_cfg(minimal_dsl(), three_sessions)
    fa = run_backtest(fixed, three_sessions)
    fb = run_backtest(fixed.model_copy(update={"seed": 5}), three_sessions)
    assert [t.as_dict() for t in fa.trades] == [t.as_dict() for t in fb.trades]


def test_out_of_order_data_raises() -> None:
    d = trading_days(date(2026, 11, 16), 1)[0]
    start = session_open_utc(d)
    bars = [make_candle(start + timedelta(minutes=i), 100, 101, 99, 100.5) for i in (0, 2, 1)]
    with pytest.raises(DataOrderError):
        HistoricalFeed(bars, Timeframe.M1, CAL)


def test_duplicates_are_dropped_and_bars_resample() -> None:
    days = trading_days(date(2026, 11, 16), 1)
    bars = linear_sessions(days, bars_per_session=12)
    bars.insert(3, bars[2])  # duplicate timestamp
    feed = HistoricalFeed(bars, Timeframe.M5, CAL)
    assert len(feed) == 3  # 12 minutes -> 5m buckets 09:15, 09:20, 09:25(2 bars)
    assert feed.bars[0].open == Decimal(100) and feed.bars[0].close == Decimal("104.5")
    evs = list(feed.events())
    ts = [e.ts for e in evs]
    assert ts == sorted(ts), "events must be time-ordered"
    kinds = [e.kind for e in evs]
    assert kinds[0] == "bar" and kinds[1] == "open" and kinds[-1] == "session_end"


def test_no_lookahead_last_bar_signal_cannot_fill(make_cfg) -> None:  # type: ignore[no-untyped-def]
    """Only the very last bar satisfies the entry condition: the signal is real, but there
    is no later price to fill it on, so the backtest must contain zero trades."""
    days = trading_days(date(2026, 11, 16), 1)
    candles = linear_sessions(days, bars_per_session=30)
    last = candles[-1]
    candles[-1] = last.model_copy(update={"close": Decimal(5000), "high": Decimal(5000)})
    dsl = minimal_dsl(
        entry={
            "long": {
                "kind": "compare",
                "left": {"kind": "price", "field": "close"},
                "op": "gt",
                "right": {"kind": "const", "value": 1000},
            }
        }
    )
    res = run_backtest(make_cfg(dsl, candles), candles)
    assert res.stats["signals"] == 1
    assert res.trades == []
    assert res.stats["orders"] == 1  # submitted, then cancelled at session end


def test_warmup_excludes_trades(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    dsl = minimal_dsl(
        indicators={"ema21": {"type": "EMA", "params": {"period": 21}}},
        exit={"time_exit_bars": 1},
    )
    res = run_backtest(make_cfg(dsl, three_sessions), three_sessions)
    warm = res.assumptions["warmup_bars"]
    assert warm >= 21
    assert res.trades, res.stats
    assert all(t.bar_index_entry is not None and t.bar_index_entry >= warm for t in res.trades)


def test_end_of_data_flatten(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    dsl = minimal_dsl(exit={"time_exit_bars": 500})
    res = run_backtest(make_cfg(dsl, three_sessions), three_sessions)
    assert res.assumptions["end_of_data_flatten"] is True
    assert res.trades and res.trades[-1].exit_reason == "square_off: end of data"
    assert res.trades[-1].exit_at > three_sessions[-1].ts
    assert any("flattened" in w for w in res.warnings)


def test_bar_close_fill_mode_is_optimistic(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    nxt = run_backtest(make_cfg(minimal_dsl(), three_sessions), three_sessions)
    cls = run_backtest(
        make_cfg(minimal_dsl(), three_sessions, fill_mode="bar_close"), three_sessions
    )
    # the close print of bar i and the open print of bar i+1 are the same instant; only the
    # price differs: bar_close fills at the signalling bar's close (104.5 + 5 bps),
    # next_bar_open at the next bar's open (105 + 5 bps)
    assert cls.trades[0].entry_at == nxt.trades[0].entry_at
    assert cls.trades[0].entry_price < nxt.trades[0].entry_price
    assert cls.assumptions["fill_mode"] == "bar_close"


def test_daily_loss_limit_halts_entries(make_cfg, candle_factory) -> None:  # type: ignore[no-untyped-def]
    mc = candle_factory
    days = trading_days(date(2026, 11, 16), 2)
    # falling market: open = 200 - minute index -> every long loses
    candles = []
    for di, d in enumerate(days):
        start = session_open_utc(d)
        for i in range(40):
            o = 500 - 50 * di - 3 * i
            candles.append(mc(start + timedelta(minutes=i), o, o + 0.5, o - 4, o - 3.5))
    dsl = minimal_dsl(max_trades_per_day=20, exit={"time_exit_bars": 1})
    dsl["position_sizing"] = {"method": "fixed_quantity", "quantity": 100}
    from risk.limits import RiskLimits

    cfg = make_cfg(
        dsl,
        candles,
        initial_capital=Decimal(100000),
        risk_limits=RiskLimits(max_daily_loss_pct=0.5),
    )
    res = run_backtest(cfg, candles)
    assert res.stats["halted"] in ("daily loss limit", None)
    assert any(
        k.startswith("halted") or "daily loss" in k
        for k in {**res.stats["risk_rejections"], **res.stats["engine_gate"]}
    ), res.stats
    assert res.metrics.total_return is not None and res.metrics.total_return < 0
    # Never lost much more than the cap in a single day (cap 500 + one trade of overshoot)
    for i in range(1, len(res.equity_curve)):
        day_change = res.equity_curve[i][1] - res.equity_curve[i - 1][1]
        assert day_change > Decimal(-2000)


def test_metrics_edge_cases() -> None:
    m = compute_metrics([], [], initial_capital=Decimal(1000), bars_total=0, bars_in_position=0)
    assert m.total_trades == 0 and m.sharpe is None and m.win_rate_pct is None
    assert m.profit_factor is None and m.expectancy is None and m.exposure_time_pct is None
    assert m.final_equity == 1000.0
    d = m.as_dict()
    assert all(v == v for v in d.values() if isinstance(v, float))  # no NaN
