"""Walk-forward: optimise on a training window, test the chosen parameters on the next
unseen window, roll forward. Only the stitched out-of-sample equity is honest."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from backtest.config import BacktestConfig
from backtest.metrics import Metrics, compute_metrics, drawdown_curve
from backtest.optimize import Objective, ParamSpace, _objective, optimize
from backtest.runner import BacktestResult, TradeRecord, run_backtest
from core.models import Candle
from core.time import ensure_utc
from risk.market_history import PcrHistory
from strategy.option_features import ChainHistory


@dataclass(frozen=True)
class Window:
    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


@dataclass
class WindowResult:
    window: Window
    params: dict[str, Any]
    in_sample: Metrics
    out_of_sample: Metrics
    oos_trades: int
    oos_result: BacktestResult


@dataclass
class WalkForwardResult:
    objective: str
    windows: list[WindowResult]
    oos_equity: list[tuple[datetime, Decimal]]
    oos_drawdown: list[tuple[datetime, float]]
    oos_metrics: Metrics
    oos_trades: list[TradeRecord]
    is_oos_ratio: float | None  # mean OOS objective / mean IS objective
    flags: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "windows": [
                {
                    "index": w.window.index,
                    "train": [w.window.train_start.isoformat(), w.window.train_end.isoformat()],
                    "test": [w.window.test_start.isoformat(), w.window.test_end.isoformat()],
                    "params": w.params,
                    "in_sample": w.in_sample.as_dict(),
                    "out_of_sample": w.out_of_sample.as_dict(),
                    "oos_trades": w.oos_trades,
                }
                for w in self.windows
            ],
            "oos_equity": [(ts.isoformat(), str(eq)) for ts, eq in self.oos_equity],
            "oos_drawdown": [(ts.isoformat(), dd) for ts, dd in self.oos_drawdown],
            "oos_metrics": self.oos_metrics.as_dict(),
            "oos_trades": [t.as_dict() for t in self.oos_trades],
            "is_oos_ratio": self.is_oos_ratio,
            "flags": self.flags,
        }


def make_windows(
    start: datetime, end: datetime, train_days: int, test_days: int, step_days: int
) -> list[Window]:
    """Test periods never overlap and tile [start + train, end) in `step_days` strides."""
    start, end = ensure_utc(start), ensure_utc(end)
    if step_days <= 0 or train_days <= 0 or test_days <= 0:
        raise ValueError("train_days, test_days and step_days must be positive")
    if step_days < test_days:
        raise ValueError("step_days must be >= test_days so test periods do not overlap")
    out: list[Window] = []
    i = 0
    cursor = start
    while True:
        train_end = cursor + timedelta(days=train_days)
        test_end = min(train_end + timedelta(days=test_days), end)
        if train_end >= end:
            break
        out.append(Window(i, cursor, train_end, train_end, test_end))
        i += 1
        cursor = cursor + timedelta(days=step_days)
        if test_end >= end:
            break
    return out


def walk_forward(
    cfg: BacktestConfig,
    candles: Sequence[Candle],
    space: ParamSpace,
    *,
    train_days: int,
    test_days: int,
    step_days: int | None = None,
    objective: Objective = "sharpe",
    max_runs_per_window: int = 100,
    progress: Callable[[float], None] | None = None,
    market_history: PcrHistory | None = None,
    option_history: ChainHistory | None = None,
) -> WalkForwardResult:
    windows = make_windows(cfg.start, cfg.end, train_days, test_days, step_days or test_days)
    results: list[WindowResult] = []
    stitched: list[tuple[datetime, Decimal]] = []
    all_trades: list[TradeRecord] = []
    equity = cfg.initial_capital
    bars_total = 0
    bars_in_pos = 0
    for n, w in enumerate(windows):
        train_cfg = cfg.model_copy(update={"start": w.train_start, "end": w.train_end})
        opt = optimize(
            train_cfg,
            candles,
            space,
            objective=objective,
            max_runs=max_runs_per_window,
            market_history=market_history,
            option_history=option_history,
        )
        if opt.best is None:
            continue
        params = opt.best.params
        test_cfg = cfg.with_overrides(params).model_copy(
            update={"start": w.test_start, "end": w.test_end, "initial_capital": equity}
        )
        oos = run_backtest(
            test_cfg, candles, market_history=market_history, option_history=option_history
        )
        results.append(
            WindowResult(w, params, opt.best.metrics, oos.metrics, oos.metrics.total_trades, oos)
        )
        for ts, eq in oos.equity_curve:
            stitched.append((ts, eq))
        all_trades.extend(oos.trades)
        bars_total += max(0, oos.bars - oos.assumptions.get("warmup_bars", 0))
        bars_in_pos += int(oos.stats.get("bars_in_position", 0))
        if oos.equity_curve:
            equity = oos.equity_curve[-1][1]
        if progress is not None:
            progress((n + 1) / len(windows) * 100)
    oos_metrics = compute_metrics(
        all_trades,
        stitched,
        initial_capital=cfg.initial_capital,
        bars_total=bars_total,
        bars_in_position=bars_in_pos,
    )
    is_vals = [v for r in results if (v := _objective(r.in_sample, objective)) is not None]
    oos_vals = [v for r in results if (v := _objective(r.out_of_sample, objective)) is not None]
    ratio: float | None = None
    if is_vals and oos_vals:
        mean_is = sum(is_vals) / len(is_vals)
        mean_oos = sum(oos_vals) / len(oos_vals)
        ratio = (mean_oos / mean_is) if mean_is else None
    flags: list[str] = []
    if not results:
        flags.append("no windows produced results (range too short for train+test)")
    if ratio is not None and ratio < 0.5:
        flags.append(f"out-of-sample {objective} is {ratio:.0%} of in-sample: likely over-fit")
    if (
        results
        and sum(1 for r in results if (r.out_of_sample.total_return or 0) > 0) < len(results) / 2
    ):
        flags.append("fewer than half of the test windows were profitable")
    return WalkForwardResult(
        objective=objective,
        windows=results,
        oos_equity=stitched,
        oos_drawdown=drawdown_curve(stitched),
        oos_metrics=oos_metrics,
        oos_trades=all_trades,
        is_oos_ratio=ratio,
        flags=flags,
    )
