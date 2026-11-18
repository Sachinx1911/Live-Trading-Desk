"""Execution: orders, simulator, costs, position book, and the single live gateway.

`execution.live.upstox_orders` is deliberately not exported: only the gateway may use it."""

from execution.costs import CostBreakdown, CostModel, StaticCostSchedule
from execution.orders import IdempotencyIndex, InvalidTransition, Order, OrderEvent, transition
from execution.simulator import (
    ClosedTrade,
    ExecutionSimulator,
    FixedBpsSlippage,
    MarketState,
    PositionBook,
    SpreadAwareSlippage,
)

__all__ = [
    "ClosedTrade",
    "CostBreakdown",
    "CostModel",
    "ExecutionSimulator",
    "FixedBpsSlippage",
    "IdempotencyIndex",
    "InvalidTransition",
    "MarketState",
    "Order",
    "OrderEvent",
    "PositionBook",
    "SpreadAwareSlippage",
    "StaticCostSchedule",
    "transition",
]
