"""Order record and state machine. Every status change goes through `transition`, which
enforces `core.models.enums.ORDER_TRANSITIONS` and appends an immutable event."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.models import OrderIntent, OrderStatus
from core.models.enums import can_transition
from core.time import utcnow


class InvalidTransition(Exception):  # noqa: N818 - name fixed by the package contract
    def __init__(self, order_id: UUID, src: OrderStatus, dst: OrderStatus) -> None:
        super().__init__(f"order {order_id}: {src.value} -> {dst.value} is not allowed")
        self.order_id, self.src, self.dst = order_id, src, dst


class OrderEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_status: OrderStatus
    to_status: OrderStatus
    ts: datetime
    fill_qty: int | None = None
    fill_px: Decimal | None = None
    reason: str
    source: str = Field(description="simulator | gateway | broker_callback | reconciliation | user")


class Order(BaseModel):
    """Mutable in-memory order. Persistence (paper_orders / live_orders) is the caller's job."""

    order_id: UUID = Field(default_factory=uuid4)
    intent: OrderIntent
    status: OrderStatus = OrderStatus.INTENT
    filled_qty: int = 0
    avg_fill_price: Decimal | None = None
    broker_order_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    events: list[OrderEvent] = Field(default_factory=list)

    @property
    def remaining_qty(self) -> int:
        return self.intent.quantity - self.filled_qty

    @property
    def is_open(self) -> bool:
        return self.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}

    @property
    def instrument_id(self) -> int:
        return self.intent.instrument_id


def _apply_fill(order: Order, qty: int, px: Decimal) -> None:
    if qty <= 0 or qty > order.remaining_qty:
        raise ValueError(f"fill qty {qty} invalid for remaining {order.remaining_qty}")
    prev_qty = order.filled_qty
    prev_avg = order.avg_fill_price or Decimal(0)
    order.filled_qty = prev_qty + qty
    order.avg_fill_price = (prev_avg * prev_qty + px * qty) / order.filled_qty


def transition(
    order: Order,
    to: OrderStatus,
    *,
    reason: str,
    source: str,
    ts: datetime | None = None,
    fill: tuple[int, Decimal] | None = None,
) -> Order:
    """Move `order` to `to`, recording the event. Raises InvalidTransition otherwise.
    A fill tuple (qty, price) is applied atomically with the transition."""
    same_partial = (
        to == OrderStatus.PARTIALLY_FILLED and order.status == OrderStatus.PARTIALLY_FILLED
    )
    # A further partial fill keeps the status; it is recorded as an event, not a transition.
    if not same_partial and not can_transition(order.status, to):
        raise InvalidTransition(order.order_id, order.status, to)
    when = ts or utcnow()
    if fill is not None:
        _apply_fill(order, *fill)
        if to == OrderStatus.FILLED and order.remaining_qty != 0:
            raise ValueError("FILLED with remaining quantity")
        if to == OrderStatus.PARTIALLY_FILLED and order.remaining_qty == 0:
            raise ValueError("PARTIALLY_FILLED with nothing remaining")
    order.events.append(
        OrderEvent(
            from_status=order.status,
            to_status=to,
            ts=when,
            fill_qty=fill[0] if fill else None,
            fill_px=fill[1] if fill else None,
            reason=reason,
            source=source,
        )
    )
    order.status = to
    order.updated_at = when
    return order


class IdempotencyIndex:
    """One order per `OrderIntent.idempotency_key` (CLAUDE.md: prevent duplicate orders)."""

    def __init__(self) -> None:
        self._by_key: dict[str, UUID] = {}

    def get(self, key: str) -> UUID | None:
        return self._by_key.get(key)

    def register(self, key: str, order_id: UUID) -> bool:
        """True if registered now; False if the key was already taken (duplicate)."""
        if key in self._by_key:
            return False
        self._by_key[key] = order_id
        return True

    def __len__(self) -> int:
        return len(self._by_key)
