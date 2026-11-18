from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.models import OrderStatus
from core.models.enums import ORDER_TRANSITIONS
from execution.orders import IdempotencyIndex, InvalidTransition, Order, transition
from tests.conftest import make_intent


def test_valid_path_with_fills() -> None:
    o = Order(intent=make_intent(qty=100))
    transition(o, OrderStatus.SUBMITTED, reason="s", source="t")
    transition(o, OrderStatus.OPEN, reason="o", source="t")
    transition(o, OrderStatus.PARTIALLY_FILLED, reason="f", source="t", fill=(40, Decimal("100")))
    assert o.filled_qty == 40 and o.remaining_qty == 60
    transition(o, OrderStatus.FILLED, reason="f", source="t", fill=(60, Decimal("110")))
    assert o.avg_fill_price == Decimal("106")
    assert [e.to_status for e in o.events][-1] == OrderStatus.FILLED
    assert o.status.is_terminal


def test_invalid_transition_raises_and_leaves_state() -> None:
    o = Order(intent=make_intent())
    with pytest.raises(InvalidTransition):
        transition(o, OrderStatus.FILLED, reason="x", source="t")
    assert o.status == OrderStatus.INTENT and o.events == []


def test_filled_requires_full_quantity() -> None:
    o = Order(intent=make_intent(qty=10))
    transition(o, OrderStatus.SUBMITTED, reason="s", source="t")
    transition(o, OrderStatus.OPEN, reason="o", source="t")
    with pytest.raises(ValueError):
        transition(o, OrderStatus.FILLED, reason="f", source="t", fill=(5, Decimal(1)))


@settings(max_examples=300)
@given(st.lists(st.sampled_from(list(OrderStatus)), min_size=1, max_size=12))
def test_random_sequences_never_reach_invalid_state(path: list[OrderStatus]) -> None:
    """Whatever targets are thrown at it, the order only ever moves along the table
    (plus the explicit self-loop for additional partial fills)."""
    o = Order(intent=make_intent(qty=5))
    for target in path:
        before = o.status
        fill = None
        if target == OrderStatus.FILLED:
            fill = (o.remaining_qty, Decimal(1))
        elif target == OrderStatus.PARTIALLY_FILLED:
            fill = (1, Decimal(1))
        try:
            transition(o, target, reason="r", source="t", fill=fill)
        except (InvalidTransition, ValueError):
            assert o.status == before
            continue
        same_partial = before == target == OrderStatus.PARTIALLY_FILLED
        assert target in ORDER_TRANSITIONS[before] or same_partial
        assert o.status == target
        assert o.remaining_qty >= 0
    for e in o.events:
        assert e.to_status in ORDER_TRANSITIONS[e.from_status] or (
            e.from_status == e.to_status == OrderStatus.PARTIALLY_FILLED
        )


def test_idempotency_index() -> None:
    idx = IdempotencyIndex()
    o = Order(intent=make_intent())
    assert idx.register(o.intent.idempotency_key, o.order_id)
    assert not idx.register(o.intent.idempotency_key, o.order_id)
    assert idx.get(o.intent.idempotency_key) == o.order_id
