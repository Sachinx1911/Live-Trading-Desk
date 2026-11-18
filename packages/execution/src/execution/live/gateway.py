"""THE single path to a broker's order API (ADR-007, CLAUDE.md rule 2).

Five gates, in order, all mandatory:
  1. live trading enabled (settings flag) and the strategy version is approved_live
  2. broker session valid
  3. risk engine ALLOW
  4. daily / weekly loss limit not breached
  5. kill switch off (global, account, strategy)
plus idempotency: a repeated key returns the existing order without touching the broker.

The gateway does not decide any of these itself; the caller supplies `GateInputs` from
the authoritative sources (DB, risk engine, Redis). It only refuses or forwards."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from core.models import OrderIntent, OrderStatus
from execution.orders import IdempotencyIndex, Order, transition

SOURCE = "gateway"


class BrokerOrderClient(Protocol):
    async def place(self, intent: OrderIntent) -> str:
        """Place and return the broker's order id. Raise on rejection."""

    async def modify(
        self, broker_order_id: str, *, quantity: int | None, price: object
    ) -> None: ...

    async def cancel(self, broker_order_id: str) -> None: ...


@dataclass(frozen=True)
class GateInputs:
    live_trading_enabled: bool
    version_approved_live: bool
    broker_session_valid: bool
    risk_allowed: bool
    daily_loss_breached: bool
    kill_switch_scopes: tuple[str, ...] = ()  # non-empty => active
    risk_reasons: tuple[str, ...] = ()
    weekly_loss_breached: bool = False


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    gate_failed: str | None
    reasons: tuple[str, ...]
    order: Order | None
    duplicate: bool = False

    @property
    def broker_order_id(self) -> str | None:
        return self.order.broker_order_id if self.order else None


@dataclass
class LiveOrderRegistry:
    """Per-process registry; the DB (`live_orders.idempotency_key` unique) is the durable one."""

    index: IdempotencyIndex = field(default_factory=IdempotencyIndex)
    orders: dict[UUID, Order] = field(default_factory=dict)


def evaluate_gates(g: GateInputs) -> tuple[str | None, tuple[str, ...]]:
    if not g.live_trading_enabled:
        return "enabled", ("LIVE_TRADING_ENABLED is false",)
    if not g.version_approved_live:
        return "approval", ("strategy version is not approved_live",)
    if not g.broker_session_valid:
        return "broker_session", ("broker session invalid or expired",)
    if not g.risk_allowed:
        return "risk", g.risk_reasons or ("risk engine rejected",)
    if g.daily_loss_breached or g.weekly_loss_breached:
        return "loss_limit", ("daily/weekly loss limit breached",)
    if g.kill_switch_scopes:
        return "kill_switch", tuple(f"kill switch active: {s}" for s in g.kill_switch_scopes)
    return None, ()


async def submit_live_order(
    intent: OrderIntent,
    *,
    gates: GateInputs,
    broker: BrokerOrderClient,
    registry: LiveOrderRegistry,
) -> GateResult:
    existing = registry.index.get(intent.idempotency_key)
    if existing is not None:
        return GateResult(
            True, None, ("duplicate: existing order returned",), registry.orders[existing], True
        )

    order = Order(intent=intent)
    registry.orders[order.order_id] = order
    registry.index.register(intent.idempotency_key, order.order_id)

    failed, reasons = evaluate_gates(gates)
    if failed is not None:
        transition(
            order,
            OrderStatus.REJECTED,
            reason=f"gate:{failed}: {'; '.join(reasons)}",
            source=SOURCE,
        )
        return GateResult(False, failed, reasons, order)

    try:
        broker_id = await broker.place(intent)
    except Exception as exc:
        transition(order, OrderStatus.SUBMITTED, reason="sent to broker", source=SOURCE)
        transition(order, OrderStatus.BROKER_REJECTED, reason=str(exc), source="broker_callback")
        return GateResult(False, "broker", (str(exc),), order)
    order.broker_order_id = broker_id
    transition(order, OrderStatus.SUBMITTED, reason=f"broker accepted {broker_id}", source=SOURCE)
    return GateResult(True, None, (), order)
