"""Owner rule `pcr_guard` inside backtests (Mark 1, Stage 2): with stored PCR history the rule
blocks exactly as in paper trading; without history it is reported as skipped."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from _synth import linear_sessions, minimal_dsl, trading_days

from backtest.config import BacktestConfig
from backtest.runner import run_backtest
from core.models import AssetClass, Instrument, OptionType, Segment
from risk.market_history import PcrHistory, PcrPoint

PUT = Instrument(
    instrument_id=1,
    exchange="NSE",
    segment=Segment.OPTIONS,
    asset_class=AssetClass.INDEX,
    symbol="NIFTY25NOV25000PE",
    name="NIFTY 25000 PE",
    underlying_symbol="NIFTY",
    expiry=date(2026, 11, 26),
    strike=Decimal(25000),
    option_type=OptionType.PE,
    lot_size=75,
    tick_size=Decimal("0.05"),
)


def _run(history: PcrHistory | None):  # type: ignore[no-untyped-def]
    candles = linear_sessions(trading_days(date(2026, 11, 16), 2))
    cfg = BacktestConfig(
        strategy_version_id=1,
        dsl=minimal_dsl(position_sizing={"method": "fixed_quantity", "quantity": 75}),
        instrument=PUT,
        start=candles[0].ts,
        end=candles[-1].ts + timedelta(days=1),
        seed=42,
    )
    return run_backtest(cfg, candles, market_history=history), candles


def _history(pcr: str, candles) -> PcrHistory:  # type: ignore[no-untyped-def]
    # One point every 3 minutes across the run, like the collector stores.
    t, end = candles[0].ts - timedelta(minutes=1), candles[-1].ts
    pts = []
    while t <= end:
        pts.append(PcrPoint(t, Decimal(pcr), "2026-11-26"))
        t += timedelta(minutes=3)
    return PcrHistory(pts)


def test_high_pcr_history_blocks_put_buys() -> None:
    _, candles = _run(None)
    res, _ = _run(_history("2.5", candles))
    assert res.trades == []
    blocks = {k: v for k, v in res.stats["risk_rejections"].items() if "PCR" in k}
    assert blocks and sum(blocks.values()) >= 1
    assert res.assumptions["owner_rules_market_data"]["pcr_points"] > 0


def test_normal_pcr_history_lets_put_buys_through() -> None:
    _, candles = _run(None)
    res, _ = _run(_history("1.0", candles))
    assert res.trades
    assert not any("PCR" in k for k in res.stats["risk_rejections"])


def test_without_history_rule_is_skipped_and_reported() -> None:
    res, _ = _run(None)
    assert res.trades
    assert str(res.assumptions["owner_rules_market_data"]).startswith("none")


def test_dsl_option_operand_drives_entries() -> None:
    """DSL 1.1: an entry on `pcr < 1` trades only where the stored chain says so."""
    from _synth import TEST_INSTRUMENT

    from strategy.option_features import ChainHistory

    candles = linear_sessions(trading_days(date(2026, 11, 16), 2))
    dsl = minimal_dsl(
        dsl_schema_version="1.1",
        entry={
            "long": {
                "kind": "compare",
                "left": {"kind": "option", "feature": "pcr"},
                "op": "lt",
                "right": {"kind": "const", "value": 1},
            }
        },
    )
    cfg = BacktestConfig(
        strategy_version_id=1,
        dsl=dsl,
        instrument=TEST_INSTRUMENT,
        start=candles[0].ts,
        end=candles[-1].ts + timedelta(days=1),
        seed=42,
    )

    def chain(ce: int, pe: int) -> ChainHistory:
        rows = [
            {"strike": 100, "option_type": "CE", "oi": ce},
            {"strike": 100, "option_type": "PE", "oi": pe},
        ]
        t, end, snaps = candles[0].ts - timedelta(minutes=1), candles[-1].ts, []
        while t <= end:
            snaps.append((t, 100, rows))
            t += timedelta(minutes=3)
        return ChainHistory.from_snapshots(snaps)

    low = run_backtest(cfg, candles, option_history=chain(ce=1000, pe=500))  # PCR 0.5
    high = run_backtest(cfg, candles, option_history=chain(ce=500, pe=1000))  # PCR 2.0
    none = run_backtest(cfg, candles)  # no chain stored: the operand has no value
    assert low.trades
    assert high.trades == [] and none.trades == []
    assert low.assumptions["option_chain_snapshots"] > 0


def test_optimisation_and_comparison_see_the_same_history() -> None:
    """Optimise / compare runs get the chain history too, so pcr_guard blocks there as well."""
    from backtest.compare import compare
    from backtest.optimize import optimize

    base, candles = _run(None)
    hist = _history("2.5", candles)
    cfg = BacktestConfig(
        strategy_version_id=1,
        dsl=minimal_dsl(position_sizing={"method": "fixed_quantity", "quantity": 75}),
        instrument=PUT,
        start=candles[0].ts,
        end=candles[-1].ts + timedelta(days=1),
        seed=42,
    )
    space = {"position_sizing.quantity": [75, 150]}
    with_hist = optimize(cfg, candles, space, market_history=hist, keep_results=True)
    without = optimize(cfg, candles, space, keep_results=True)
    assert all(r.trades == [] for r in with_hist.results.values())
    assert any(r.trades for r in without.results.values())

    cmp = compare([cfg], {PUT.instrument_id: candles}, market_history_by_instrument={1: hist})
    assert cmp.rows[0].result.trades == []
    assert base.trades
