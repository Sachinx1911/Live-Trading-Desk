from __future__ import annotations

import itertools
import time
from datetime import UTC, date, datetime

from _synth import (
    TEST_INSTRUMENT,
    linear_sessions,
    minimal_dsl,
    random_walk_sessions,
    trading_days,
)

from backtest.compare import compare
from backtest.optimize import grid, optimize, random_search
from backtest.runner import run_backtest
from backtest.walk_forward import make_windows, walk_forward
from strategy.dsl.examples import load_example


def test_grid_and_random_sizes() -> None:
    space = {"a": [1, 2, 3], "b": ["x", "y"]}
    assert len(list(grid(space))) == 6
    rs = list(random_search(space, 4, seed=1))
    assert len(rs) == 4 and len({tuple(sorted(r.items())) for r in rs}) == 4
    assert len(list(random_search(space, 50))) == 6  # capped at the grid size


def test_optimize_ranks_by_objective(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    cfg = make_cfg(minimal_dsl(), three_sessions)
    space = {"exit.time_exit_bars": [2, 3, 4], "position_sizing.quantity": [10, 20]}
    out = optimize(cfg, three_sessions, space, objective="net_pnl", max_runs=50)
    assert out.runs == 6 and len(out.rows) == 6
    vals = [r.objective_value for r in out.rows]
    assert vals == sorted((v for v in vals if v is not None), reverse=True)
    assert out.best is not None and out.best.rank == 1
    assert set(out.sensitivity) == set(space)
    assert out.overfit_flags  # tiny sample: "only N trades" flag must fire
    # each row is a real run with its own hash
    assert len({r.config_hash for r in out.rows}) == 6


def test_walk_forward_windows_tile_without_overlap() -> None:
    s = datetime(2026, 1, 1, tzinfo=UTC)
    e = datetime(2026, 3, 1, tzinfo=UTC)
    ws = make_windows(s, e, train_days=20, test_days=10, step_days=10)
    assert ws, "range should yield windows"
    for a, b in itertools.pairwise(ws):
        assert a.test_end <= b.test_start
        assert b.train_start == a.train_start.__class__.fromtimestamp(
            a.train_start.timestamp() + 10 * 86400, tz=UTC
        )
    assert ws[0].test_start == ws[0].train_end
    assert ws[-1].test_end <= e


def test_walk_forward_runs(make_cfg) -> None:  # type: ignore[no-untyped-def]
    days = trading_days(date(2026, 11, 2), 8)
    candles = linear_sessions(days, bars_per_session=30)
    cfg = make_cfg(minimal_dsl(), candles)
    wf = walk_forward(
        cfg,
        candles,
        {"exit.time_exit_bars": [2, 3]},
        train_days=4,
        test_days=2,
        objective="net_pnl",
    )
    assert wf.windows, wf.flags
    assert wf.oos_equity and wf.oos_metrics.total_trades >= 1
    assert all(w.params["exit.time_exit_bars"] in (2, 3) for w in wf.windows)
    d = wf.as_dict()
    assert d["windows"][0]["test"][0] >= d["windows"][0]["train"][1]


def test_compare_uses_identical_assumptions(make_cfg, three_sessions) -> None:  # type: ignore[no-untyped-def]
    a = make_cfg(minimal_dsl(), three_sessions, label="A", seed=1)
    b = make_cfg(
        minimal_dsl(exit={"time_exit_bars": 4}),
        three_sessions,
        label="B",
        seed=2,
        strategy_version_id=2,
    )
    cmp_ = compare([a, b], {TEST_INSTRUMENT.instrument_id: three_sessions})
    assert [r.label for r in cmp_.rows] == ["A", "B"]
    assert cmp_.rows[0].result.assumptions["seed"] == cmp_.rows[1].result.assumptions["seed"] == 1
    assert cmp_.rows[0].metrics["total_trades"] == 3


def test_ema_example_runs_fast(make_cfg) -> None:  # type: ignore[no-untyped-def]
    days = trading_days(date(2026, 8, 3), 60)
    candles = random_walk_sessions(days)
    dsl = load_example("ema_rsi_nifty")
    dsl["universe"] = {"kind": "instrument", "instrument_ids": ["1"]}
    cfg = make_cfg(dsl, candles)
    t0 = time.perf_counter()
    res = run_backtest(cfg, candles)
    elapsed = time.perf_counter() - t0
    assert elapsed < 10, elapsed
    assert res.bars > 4000  # 60 sessions x 75 five-minute bars
    assert (res.metrics.total_trades >= 0 and not res.warnings) or all(
        "flattened" in w for w in res.warnings
    )
    assert len(res.equity_curve) == 60
