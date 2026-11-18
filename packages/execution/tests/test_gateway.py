import pytest

from core.models import OrderIntent, OrderStatus
from execution.live.gateway import GateInputs, LiveOrderRegistry, submit_live_order
from tests.conftest import make_intent


class FakeBroker:
    def __init__(self, fail: bool = False) -> None:
        self.placed: list[OrderIntent] = []
        self.fail = fail

    async def place(self, intent: OrderIntent) -> str:
        self.placed.append(intent)
        if self.fail:
            raise RuntimeError("UDAPI1061 insufficient funds")
        return f"brk-{len(self.placed)}"

    async def modify(
        self, broker_order_id: str, *, quantity: int | None, price: object
    ) -> None: ...

    async def cancel(self, broker_order_id: str) -> None: ...


ALL_PASS = GateInputs(
    live_trading_enabled=True,
    version_approved_live=True,
    broker_session_valid=True,
    risk_allowed=True,
    daily_loss_breached=False,
)


async def test_all_gates_pass_places_once_and_duplicate_returns_existing() -> None:
    broker, reg = FakeBroker(), LiveOrderRegistry()
    intent = make_intent()
    r1 = await submit_live_order(intent, gates=ALL_PASS, broker=broker, registry=reg)
    assert r1.accepted and r1.order is not None and r1.order.status == OrderStatus.SUBMITTED
    assert r1.broker_order_id == "brk-1"
    r2 = await submit_live_order(intent, gates=ALL_PASS, broker=broker, registry=reg)
    assert r2.duplicate and r2.order is r1.order and len(broker.placed) == 1


@pytest.mark.parametrize(
    ("field", "value", "gate"),
    [
        ("live_trading_enabled", False, "enabled"),
        ("version_approved_live", False, "approval"),
        ("broker_session_valid", False, "broker_session"),
        ("risk_allowed", False, "risk"),
        ("daily_loss_breached", True, "loss_limit"),
        ("weekly_loss_breached", True, "loss_limit"),
        ("kill_switch_scopes", ("global",), "kill_switch"),
    ],
)
async def test_each_gate_refuses_without_calling_broker(
    field: str, value: object, gate: str
) -> None:
    broker, reg = FakeBroker(), LiveOrderRegistry()
    gates = GateInputs(**{**ALL_PASS.__dict__, field: value})
    r = await submit_live_order(make_intent(), gates=gates, broker=broker, registry=reg)
    assert not r.accepted and r.gate_failed == gate
    assert r.order is not None and r.order.status == OrderStatus.REJECTED
    assert broker.placed == []


async def test_gate_order_is_fixed_first_failure_reported() -> None:
    broker, reg = FakeBroker(), LiveOrderRegistry()
    gates = GateInputs(
        live_trading_enabled=True,
        version_approved_live=False,
        broker_session_valid=False,
        risk_allowed=False,
        daily_loss_breached=True,
        kill_switch_scopes=("global",),
    )
    r = await submit_live_order(make_intent(), gates=gates, broker=broker, registry=reg)
    assert r.gate_failed == "approval"


async def test_broker_rejection_is_recorded() -> None:
    broker, reg = FakeBroker(fail=True), LiveOrderRegistry()
    r = await submit_live_order(make_intent(), gates=ALL_PASS, broker=broker, registry=reg)
    assert not r.accepted and r.gate_failed == "broker"
    assert r.order is not None and r.order.status == OrderStatus.BROKER_REJECTED
