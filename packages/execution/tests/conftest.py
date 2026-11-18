from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from core.models import (
    DepthLevel,
    OrderIntent,
    OrderSide,
    OrderType,
    ProductType,
    Quote,
    TradingMode,
)

T0 = datetime(2026, 11, 17, 4, 0, tzinfo=UTC)  # 09:30 IST, Tuesday


def make_intent(
    side: OrderSide = OrderSide.BUY,
    qty: int = 100,
    order_type: OrderType = OrderType.MARKET,
    limit: Decimal | None = None,
    trigger: Decimal | None = None,
    instrument_id: int = 22,
    product: ProductType = ProductType.INTRADAY,
    key: str | None = None,
) -> OrderIntent:
    sid = uuid4()
    return OrderIntent(
        signal_id=sid,
        strategy_version_id=1,
        account_id=1,
        mode=TradingMode.PAPER,
        instrument_id=instrument_id,
        side=side,
        order_type=order_type,
        product=product,
        quantity=qty,
        limit_price=limit,
        trigger_price=trigger,
        idempotency_key=key or OrderIntent.make_key(1, sid),
    )


def make_quote(
    ltp: str,
    bid: str | None = None,
    ask: str | None = None,
    bid_qty: int | None = None,
    ask_qty: int | None = None,
    ts: datetime = T0,
    instrument_id: int = 22,
) -> Quote:
    return Quote(
        instrument_id=instrument_id,
        ts=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid) if bid else None,
        ask=Decimal(ask) if ask else None,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        provider_id="fake",
        received_at=ts,
        is_demo=True,
    )


@pytest.fixture
def t0() -> datetime:
    return T0


__all__ = ["DepthLevel", "make_intent", "make_quote"]
