"""Parameter sweeps with plateau/overfitting diagnostics. A sweep is many independent
backtests on the same data; ranking is by one objective, but the result keeps every metric
so a user can see what the "best" number cost elsewhere."""

from __future__ import annotations

import itertools
import random
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from backtest.config import BacktestConfig
from backtest.metrics import Metrics
from backtest.runner import BacktestResult, run_backtest
from core.models import Candle
from risk.market_history import PcrHistory
from strategy.option_features import ChainHistory

Objective = Literal["sharpe", "net_pnl", "calmar", "expectancy", "profit_factor", "sortino"]
ParamSpace = dict[str, Sequence[Any]]

OBJECTIVE_GETTER: dict[str, Callable[[Metrics], float | None]] = {
    "sharpe": lambda m: m.sharpe,
    "net_pnl": lambda m: m.total_return,
    "calmar": lambda m: m.calmar,
    "expectancy": lambda m: m.expectancy,
    "profit_factor": lambda m: m.profit_factor,
    "sortino": lambda m: m.sortino,
}


def grid(space: ParamSpace) -> Iterator[dict[str, Any]]:
    keys = list(space)
    for combo in itertools.product(*(space[k] for k in keys)):
        yield dict(zip(keys, combo, strict=True))


def random_search(space: ParamSpace, n: int, seed: int = 42) -> Iterator[dict[str, Any]]:
    rng = random.Random(seed)  # noqa: S311 - sampling, not security
    keys = list(space)
    seen: set[tuple[Any, ...]] = set()
    total = 1
    for k in keys:
        total *= len(space[k])
    n = min(n, total)
    while len(seen) < n:
        combo = tuple(rng.choice(list(space[k])) for k in keys)
        if combo in seen:
            continue
        seen.add(combo)
        yield dict(zip(keys, combo, strict=True))


@dataclass(frozen=True)
class OptimizationRow:
    rank: int
    params: dict[str, Any]
    objective_value: float | None
    metrics: Metrics
    config_hash: str
    trades: int


@dataclass
class OptimizationResult:
    objective: str
    rows: list[OptimizationRow]
    sensitivity: dict[str, list[dict[str, Any]]]
    plateau_score: float | None
    overfit_flags: list[str]
    runs: int
    best: OptimizationRow | None = None
    results: dict[str, BacktestResult] = field(default_factory=dict)  # config_hash -> result

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "runs": self.runs,
            "plateau_score": self.plateau_score,
            "overfit_flags": self.overfit_flags,
            "best": None if self.best is None else self.best.params,
            "rows": [
                {
                    "rank": r.rank,
                    "params": r.params,
                    "objective_value": r.objective_value,
                    "trades": r.trades,
                    "metrics": r.metrics.as_dict(),
                    "config_hash": r.config_hash,
                }
                for r in self.rows
            ],
            "sensitivity": self.sensitivity,
        }


def _objective(metrics: Metrics, objective: str) -> float | None:
    return OBJECTIVE_GETTER[objective](metrics)


def _rank(
    rows: list[tuple[dict[str, Any], BacktestResult]], objective: str
) -> list[OptimizationRow]:
    scored = []
    for params, res in rows:
        v = _objective(res.metrics, objective)
        scored.append((params, res, v))
    # None (undefined objective, e.g. no trades) ranks last
    scored.sort(key=lambda t: (t[2] is None, -(t[2] or 0.0)))
    return [
        OptimizationRow(
            rank=i + 1,
            params=params,
            objective_value=v,
            metrics=res.metrics,
            config_hash=res.config_hash,
            trades=res.metrics.total_trades,
        )
        for i, (params, res, v) in enumerate(scored)
    ]


def sensitivity(
    rows: Sequence[OptimizationRow],
) -> tuple[dict[str, list[dict[str, Any]]], float | None]:
    """Per parameter: objective averaged over the other parameters at each value; plateau
    score = fraction of the best row's one-step neighbours (per parameter) whose objective
    is within 20% of the best. 1.0 = a plateau, 0.0 = a needle (classic overfit)."""
    if not rows:
        return {}, None
    best: OptimizationRow = rows[0]
    if best.objective_value is None:
        return {}, None
    table: dict[str, list[dict[str, Any]]] = {}
    params = list(best.params)
    for p in params:
        by_value: dict[Any, list[float]] = {}
        for r in rows:
            if r.objective_value is None:
                continue
            by_value.setdefault(r.params[p], []).append(r.objective_value)
        vals = sorted(by_value, key=lambda v: (isinstance(v, str), v))
        table[p] = [
            {"value": v, "mean": sum(by_value[v]) / len(by_value[v]), "n": len(by_value[v])}
            for v in vals
        ]
    # neighbours of the best along each parameter axis, other params fixed
    neighbours: list[float] = []
    index = {tuple(sorted(r.params.items())): r for r in rows}
    for p in params:
        vals = [row["value"] for row in table.get(p, [])]
        if best.params[p] not in vals:
            continue
        i = vals.index(best.params[p])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                key = dict(best.params)
                key[p] = vals[j]
                nb = index.get(tuple(sorted(key.items())))
                if nb is not None and nb.objective_value is not None:
                    neighbours.append(nb.objective_value)
    if not neighbours:
        return table, None
    tol = abs(best.objective_value) * 0.2
    within = sum(1 for v in neighbours if abs(best.objective_value - v) <= tol)
    return table, within / len(neighbours)


def overfit_flags(
    rows: Sequence[OptimizationRow], plateau: float | None, min_trades: int = 30
) -> list[str]:
    flags: list[str] = []
    if not rows or rows[0].objective_value is None:
        return ["no scored runs"]
    best = rows[0]
    if best.trades < min_trades:
        flags.append(f"best run has only {best.trades} trades (< {min_trades})")
    if plateau is not None and plateau < 0.5:
        flags.append(f"best parameters sit on a needle (plateau score {plateau:.2f} < 0.5)")
    scored = [r.objective_value for r in rows if r.objective_value is not None]
    if len(scored) >= 10:
        top = scored[:10]
        spread = (top[0] - top[-1]) / abs(top[0]) if top[0] else 0.0
        if spread > 0.5:
            flags.append(
                f"top-10 objective spread {spread:.0%}: results are unstable across neighbours"
            )
        median = sorted(scored)[len(scored) // 2]
        if median <= 0 < top[0]:
            flags.append("median run is unprofitable; the best run may be luck")
    return flags


def optimize(
    cfg: BacktestConfig,
    candles: Sequence[Candle],
    space: ParamSpace,
    *,
    objective: Objective = "sharpe",
    method: Literal["grid", "random"] = "grid",
    max_runs: int = 200,
    seed: int | None = None,
    progress: Callable[[float], None] | None = None,
    keep_results: bool = False,
    market_history: PcrHistory | None = None,
    option_history: ChainHistory | None = None,
) -> OptimizationResult:
    """`market_history` / `option_history`: stored chain history, passed unchanged to every
    run so owner rules and option features behave as in a single backtest (Mark 1 Stage 2)."""
    gen = grid(space) if method == "grid" else random_search(space, max_runs, seed or cfg.seed)
    combos = list(itertools.islice(gen, max_runs))
    rows: list[tuple[dict[str, Any], BacktestResult]] = []
    results: dict[str, BacktestResult] = {}
    for i, params in enumerate(combos):
        res = run_backtest(
            cfg.with_overrides(params),
            candles,
            market_history=market_history,
            option_history=option_history,
        )
        rows.append((params, res))
        if keep_results:
            results[res.config_hash] = res
        if progress is not None:
            progress((i + 1) / len(combos) * 100)
    ranked = _rank(rows, objective)
    table, plateau = sensitivity(ranked)
    return OptimizationResult(
        objective=objective,
        rows=ranked,
        sensitivity=table,
        plateau_score=plateau,
        overfit_flags=overfit_flags(ranked, plateau),
        runs=len(ranked),
        best=ranked[0] if ranked else None,
        results=results,
    )
