"""Golden test: every fill, cost and metric computed by hand for a tiny 1m series."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from _synth import CAL, linear_sessions, minimal_dsl, session_open_utc, trading_days

from backtest.config import SlippageConfig
from backtest.runner import run_backtest

TICK = Decimal("0.05")
P = Decimal("0.01")


def _tick(px: Decimal) -> Decimal:
    return (px / TICK).quantize(Decimal(1), rounding=ROUND_HALF_UP) * TICK


def _paisa(x: Decimal) -> Decimal:
    return x.quantize(P, rounding=ROUND_HALF_UP)


def intraday_equity_costs(qty: int, px: Decimal, *, buy: bool) -> Decimal:
    """Static schedule as of 2025-10: brokerage Rs 20 flat, STT 0.025% sell, NSE txn
    0.00297% both, SEBI 0.0001% both, stamp 0.003% buy, GST 18% on brok+txn+sebi."""
    notional = qty * px
    brokerage = Decimal(20)
    exchange = notional * Decimal("0.0000297")
    sebi = notional * Decimal("0.000001")
    stamp = notional * Decimal("0.00003") if buy else Decimal(0)
    stt = Decimal(0) if buy else notional * Decimal("0.00025")
    gst = (brokerage + exchange + sebi) * Decimal("0.18")
    return (
        _paisa(brokerage)
        + _paisa(stt)
        + _paisa(exchange)
        + _paisa(sebi)
        + _paisa(stamp)
        + _paisa(gst)
    )


def test_golden_three_sessions(make_cfg) -> None:  # type: ignore[no-untyped-def]
    days = trading_days(date(2026, 11, 16), 3)
    candles = linear_sessions(days, bars_per_session=30)
    cfg = make_cfg(minimal_dsl(), candles, slippage=SlippageConfig(model="fixed_bps", bps=5))
    res = run_backtest(cfg, candles)

    # One trade per session (max_trades_per_day=1). Entry signal on the first bar whose
    # close time passes the risk window (09:20 IST): bar 09:19 closes at 09:20 -> market
    # order -> fills at the 09:20 bar's open + 5 bps; exit after 2 bars at the 09:22 open - 5 bps.
    assert len(res.trades) == 3, res.stats
    expected_net = Decimal(0)
    for di, d in enumerate(days):
        t = res.trades[di]
        entry_open = Decimal(100 + 10 * di + 5)  # minute index 5 = 09:20
        exit_open = Decimal(100 + 10 * di + 7)  # minute index 7 = 09:22
        buy_px = _tick(entry_open * Decimal("1.0005"))
        sell_px = _tick(exit_open * Decimal("0.9995"))
        assert t.side.value == "buy" and t.quantity == 10
        assert t.entry_price == buy_px, (t.entry_price, buy_px)
        assert t.exit_price == sell_px, (t.exit_price, sell_px)
        assert t.entry_at == session_open_utc(d) + timedelta(minutes=5, seconds=1)
        assert t.exit_at == session_open_utc(d) + timedelta(minutes=7, seconds=1)
        gross = (sell_px - buy_px) * 10
        costs = intraday_equity_costs(10, buy_px, buy=True) + intraday_equity_costs(
            10, sell_px, buy=False
        )
        assert t.gross_pnl == gross
        assert t.costs == costs, (t.costs, costs)
        assert t.net_pnl == gross - costs
        assert t.bars_held == 2
        assert (
            t.entry_reason == "entry.long"
            and t.exit_reason is not None
            and "time exit" in t.exit_reason
        )
        # MAE/MFE from bar highs/lows while in position (bars 09:20, 09:21 closed while long)
        assert t.mae is not None and t.mfe is not None
        assert t.mae == min(Decimal(0), (entry_open - 1) - buy_px)
        assert t.mfe == (entry_open + 1 + 1) - buy_px  # high of the 09:21 bar
        expected_net += gross - costs

    # Equity: one point per session close; final = capital + sum(net)
    assert len(res.equity_curve) == 3
    assert res.equity_curve[-1][1] == Decimal(100000) + expected_net
    m = res.metrics
    assert m.total_trades == 3
    assert m.total_return == float(expected_net)
    assert m.fees_total == float(sum(t.costs for t in res.trades))
    wins = [t for t in res.trades if t.net_pnl > 0]
    assert m.wins == len(wins) and m.losses == 3 - len(wins)
    assert m.win_rate_pct == len(wins) / 3 * 100
    assert m.expectancy == float(expected_net / 3)
    # Exposure: 2 bars in position per session over 89 tradeable bars (90 minus 1 warm-up bar)
    assert m.exposure_time_pct is not None and abs(m.exposure_time_pct - (6 / 89 * 100)) < 1e-9
    assert res.assumptions["end_of_data_flatten"] is False
    assert res.stats["orders"] == 6
    assert CAL.is_trading_day(days[0])
