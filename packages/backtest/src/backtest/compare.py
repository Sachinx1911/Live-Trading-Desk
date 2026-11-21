"""Compare several strategy versions on identical data, costs, slippage and seed (Module 24)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backtest.config import BacktestConfig
from backtest.runner import BacktestResult, run_backtest
from core.models import Candle
from risk.market_history import PcrHistory
from strategy.option_features import ChainHistory

COMPARE_FIELDS = (
    "total_return",
    "total_return_pct",
    "cagr_pct",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown_pct",
    "win_rate_pct",
    "profit_factor",
    "expectancy",
    "total_trades",
    "fees_total",
    "exposure_time_pct",
)


@dataclass
class ComparisonRow:
    label: str
    strategy_version_id: int
    config_hash: str
    metrics: dict[str, Any]
    result: BacktestResult


@dataclass
class Comparison:
    rows: list[ComparisonRow]
    shared_assumptions: dict[str, Any]
    data_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "shared_assumptions": self.shared_assumptions,
            "data_hash": self.data_hash,
            "rows": [
                {
                    "label": r.label,
                    "strategy_version_id": r.strategy_version_id,
                    "config_hash": r.config_hash,
                    **{k: r.metrics.get(k) for k in COMPARE_FIELDS},
                }
                for r in self.rows
            ],
        }


def compare(
    configs: Sequence[BacktestConfig],
    candles_by_instrument: dict[int, Sequence[Candle]],
    *,
    market_history_by_instrument: dict[int, PcrHistory | None] | None = None,
    option_history_by_instrument: dict[int, ChainHistory | None] | None = None,
) -> Comparison:
    if not configs:
        raise ValueError("nothing to compare")
    base = configs[0]
    rows: list[ComparisonRow] = []
    data_hash = ""
    for cfg in configs:
        # identical assumptions: force the shared range, capital, costs, slippage and seed
        shared = cfg.model_copy(
            update={
                "start": base.start,
                "end": base.end,
                "initial_capital": base.initial_capital,
                "slippage": base.slippage,
                "cost_schedule": base.cost_schedule,
                "cost_rows": base.cost_rows,
                "seed": base.seed,
                "fill_mode": base.fill_mode,
                "risk_limits": base.risk_limits,
            }
        )
        iid = cfg.instrument.instrument_id
        candles = candles_by_instrument[iid]
        res = run_backtest(
            shared,
            candles,
            market_history=(market_history_by_instrument or {}).get(iid),
            option_history=(option_history_by_instrument or {}).get(iid),
        )
        data_hash = data_hash or res.data_hash
        rows.append(
            ComparisonRow(
                label=cfg.label or cfg.document().name,
                strategy_version_id=cfg.strategy_version_id,
                config_hash=res.config_hash,
                metrics=res.metrics.as_dict(),
                result=res,
            )
        )
    shared_assumptions = {
        "range": {"start": base.start.isoformat(), "end": base.end.isoformat()},
        "initial_capital": str(base.initial_capital),
        "slippage": base.slippage.model_dump(),
        "cost_schedule": base.cost_schedule,
        "seed": base.seed,
        "fill_mode": base.fill_mode,
    }
    return Comparison(rows=rows, shared_assumptions=shared_assumptions, data_hash=data_hash)
