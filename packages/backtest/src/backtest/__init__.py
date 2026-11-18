"""Backtesting on the single shared engine (ADR-002): same StrategyEngine, RiskEngine and
ExecutionSimulator as paper trading, driven by a historical feed instead of a live one."""

from backtest.config import BacktestConfig, SlippageConfig
from backtest.data import DataOrderError, HistoricalFeed
from backtest.metrics import Metrics, compute_metrics
from backtest.runner import BacktestResult, TradeRecord, run_backtest

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "DataOrderError",
    "HistoricalFeed",
    "Metrics",
    "SlippageConfig",
    "TradeRecord",
    "compute_metrics",
    "run_backtest",
]
