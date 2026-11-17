"""Enumerations shared across the platform. Values are stable strings stored in the DB."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum


class Segment(StrEnum):
    EQUITY = "equity"
    INDEX = "index"
    FUTURES = "futures"
    OPTIONS = "options"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CRYPTO = "crypto"


class AssetClass(StrEnum):
    STOCK = "stock"
    INDEX = "index"
    FUTURE = "future"
    OPTION = "option"
    ETF = "etf"
    COMMODITY = "commodity"
    FX = "fx"
    CRYPTO = "crypto"


class OptionType(StrEnum):
    CE = "CE"
    PE = "PE"


class Timeframe(StrEnum):
    TICK = "tick"
    S1 = "1s"
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"
    W1 = "1w"
    MN1 = "1M"

    @property
    def duration(self) -> timedelta | None:
        """Fixed bar length, or None for tick / calendar-based (weekly, monthly) frames."""
        return _TF_DURATION.get(self)

    @property
    def is_intraday(self) -> bool:
        return self in {
            Timeframe.TICK,
            Timeframe.S1,
            Timeframe.M1,
            Timeframe.M5,
            Timeframe.M15,
            Timeframe.M30,
            Timeframe.H1,
        }


_TF_DURATION: dict[Timeframe, timedelta] = {
    Timeframe.S1: timedelta(seconds=1),
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.D1: timedelta(days=1),
}


class Freshness(StrEnum):
    """How much a market data value can be trusted right now. Always shown in the UI."""

    LIVE = "live"  # < 2 s old, from a connected real provider
    DELAYED = "delayed"  # 2-30 s old
    STALE = "stale"  # > 30 s old
    DISCONNECTED = "disconnected"  # provider heartbeat lost
    DEMO = "demo"  # from the fake provider; never real money
    HISTORICAL = "historical"  # a stored value, not a live one


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"  # stop-loss market
    STOP_LIMIT = "stop_limit"


class ProductType(StrEnum):
    INTRADAY = "intraday"  # MIS; auto square-off at session end
    DELIVERY = "delivery"  # CNC
    CARRY = "carry"  # NRML (F&O overnight)


class OrderStatus(StrEnum):
    """Order state machine. Transitions after SUBMITTED come only from broker events or
    reconciliation (CLAUDE.md rule 6)."""

    INTENT = "intent"
    REJECTED = "rejected"  # refused by one of our gates, never reached the broker
    SUBMITTED = "submitted"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    BROKER_REJECTED = "broker_rejected"
    UNKNOWN = "unknown"  # no broker update; awaiting reconciliation

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.REJECTED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.BROKER_REJECTED,
        }


ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.INTENT: frozenset({OrderStatus.REJECTED, OrderStatus.SUBMITTED}),
    OrderStatus.SUBMITTED: frozenset(
        {OrderStatus.OPEN, OrderStatus.FILLED, OrderStatus.BROKER_REJECTED, OrderStatus.UNKNOWN}
    ),
    OrderStatus.OPEN: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.UNKNOWN}
    ),
    OrderStatus.UNKNOWN: frozenset(
        {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED}
    ),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.BROKER_REJECTED: frozenset(),
}


def can_transition(src: OrderStatus, dst: OrderStatus) -> bool:
    return dst in ORDER_TRANSITIONS[src]
