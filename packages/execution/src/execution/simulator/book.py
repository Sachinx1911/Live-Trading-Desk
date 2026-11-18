"""Position book: fills -> positions, realized/unrealized P&L, closed round trips.

Accounting identity kept at all times (tested with hypothesis):
    cash + sum(qty * last_price) - initial_cash == realized + unrealized
where `realized` is net of all costs as they are incurred."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from core.models import Fill, OrderSide, Position, TradingMode
from execution.orders import Order


@dataclass(frozen=True)
class ClosedTrade:
    instrument_id: int
    strategy_version_id: int | None
    side: OrderSide  # direction of the round trip: BUY = long, SELL = short
    quantity: int
    entry_at: datetime
    entry_price: Decimal
    exit_at: datetime
    exit_price: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal

    @property
    def duration_s(self) -> float:
        return (self.exit_at - self.entry_at).total_seconds()


@dataclass
class _Pos:
    quantity: int = 0  # signed
    avg_price: Decimal = Decimal(0)
    realized: Decimal = Decimal(0)  # net of costs, lifetime for the instrument
    last_price: Decimal | None = None
    strategy_version_id: int | None = None
    # round-trip tracking
    entry_at: datetime | None = None
    exit_qty: int = 0
    exit_notional: Decimal = Decimal(0)
    rt_gross: Decimal = Decimal(0)
    rt_costs: Decimal = Decimal(0)
    rt_entry_qty: int = 0
    rt_entry_price: Decimal = Decimal(0)
    rt_side: OrderSide | None = None


@dataclass
class PositionBook:
    account_id: int
    mode: TradingMode
    initial_cash: Decimal
    cash: Decimal = field(init=False)
    _pos: dict[int, _Pos] = field(default_factory=dict, init=False)
    closed: list[ClosedTrade] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    # ------------------------------------------------------------------ reads
    def position(self, instrument_id: int) -> Position:
        p = self._pos.get(instrument_id, _Pos())
        return Position(
            account_id=self.account_id,
            mode=self.mode,
            instrument_id=instrument_id,
            strategy_version_id=p.strategy_version_id,
            quantity=p.quantity,
            avg_price=p.avg_price,
            realized_pnl=p.realized,
            unrealized_pnl=self._unrealized(p),
            last_price=p.last_price,
        )

    def open_positions(self) -> list[Position]:
        return [self.position(i) for i, p in self._pos.items() if p.quantity != 0]

    @property
    def realized(self) -> Decimal:
        return sum((p.realized for p in self._pos.values()), Decimal(0))

    @property
    def unrealized(self) -> Decimal:
        return sum((self._unrealized(p) for p in self._pos.values()), Decimal(0))

    @property
    def market_value(self) -> Decimal:
        return sum(
            (Decimal(p.quantity) * (p.last_price if p.last_price is not None else p.avg_price))
            for p in self._pos.values()
        ) or Decimal(0)

    @property
    def equity(self) -> Decimal:
        return self.cash + self.market_value

    @staticmethod
    def _unrealized(p: _Pos) -> Decimal:
        if p.quantity == 0 or p.last_price is None:
            return Decimal(0)
        return (p.last_price - p.avg_price) * p.quantity

    # ------------------------------------------------------------------ writes
    def mark(self, instrument_id: int, price: Decimal) -> None:
        self._pos.setdefault(instrument_id, _Pos()).last_price = price

    def apply(self, order: Order, fill: Fill) -> ClosedTrade | None:
        """Apply a fill of `order`. Returns a ClosedTrade when the position goes flat."""
        iid = order.intent.instrument_id
        p = self._pos.setdefault(iid, _Pos())
        sign = 1 if order.intent.side == OrderSide.BUY else -1
        qty, px = fill.quantity, fill.price
        self.cash -= sign * Decimal(qty) * px + fill.costs
        p.realized -= fill.costs
        p.last_price = px
        p.strategy_version_id = order.intent.strategy_version_id

        closed: ClosedTrade | None = None
        same_direction = p.quantity == 0 or (p.quantity > 0) == (sign > 0)
        if same_direction:
            # opening / adding
            if p.quantity == 0:
                p.entry_at = fill.ts
                p.rt_side = order.intent.side
                p.rt_gross = Decimal(0)
                p.rt_costs = Decimal(0)
                p.rt_entry_qty = 0
                p.rt_entry_price = Decimal(0)
                p.exit_qty = 0
                p.exit_notional = Decimal(0)
            total = abs(p.quantity) + qty
            p.avg_price = (p.avg_price * abs(p.quantity) + px * qty) / total
            p.rt_entry_price = (p.rt_entry_price * p.rt_entry_qty + px * qty) / (
                p.rt_entry_qty + qty
            )
            p.rt_entry_qty += qty
            p.quantity += sign * qty
            p.rt_costs += fill.costs
        else:
            # reducing (possibly flipping)
            reduce_qty = min(qty, abs(p.quantity))
            pos_sign = 1 if p.quantity > 0 else -1
            gross = (px - p.avg_price) * reduce_qty * pos_sign
            p.realized += gross
            p.rt_gross += gross
            p.rt_costs += fill.costs
            p.exit_qty += reduce_qty
            p.exit_notional += px * reduce_qty
            p.quantity -= pos_sign * reduce_qty
            if p.quantity == 0:
                closed = ClosedTrade(
                    instrument_id=iid,
                    strategy_version_id=p.strategy_version_id,
                    side=p.rt_side or OrderSide.BUY,
                    quantity=p.rt_entry_qty,
                    entry_at=p.entry_at or fill.ts,
                    entry_price=p.rt_entry_price,
                    exit_at=fill.ts,
                    exit_price=p.exit_notional / p.exit_qty,
                    gross_pnl=p.rt_gross,
                    costs=p.rt_costs,
                    net_pnl=p.rt_gross - p.rt_costs,
                )
                self.closed.append(closed)
                p.avg_price = Decimal(0)
                p.entry_at = None
            leftover = qty - reduce_qty
            if leftover:
                # flip: the remainder opens a new position in the fill's direction, cost-free
                # (costs were already charged on this fill)
                p.quantity = sign * leftover
                p.avg_price = px
                p.entry_at = fill.ts
                p.rt_side = order.intent.side
                p.rt_gross = Decimal(0)
                p.rt_costs = Decimal(0)
                p.rt_entry_qty = leftover
                p.rt_entry_price = px
                p.exit_qty = 0
                p.exit_notional = Decimal(0)
        return closed
