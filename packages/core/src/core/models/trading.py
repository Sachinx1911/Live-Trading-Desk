"""Canonical trading records shared by paper, live, backtest. Mode-specific persistence is
separate (ADR-008); these are the in-memory shapes the engines exchange."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.enums import OrderSide, OrderType, ProductType, TradingMode
from core.time import ensure_utc


class Signal(BaseModel):
    """Output of the strategy engine. Has no notion of account or mode."""

    model_config = ConfigDict(frozen=True)

    signal_id: UUID = Field(default_factory=uuid4)
    strategy_version_id: int
    instrument_id: int
    ts: datetime
    side: OrderSide
    kind: str = Field(description="entry | exit | stop | target | square_off")
    reason: str = Field(description="Human-readable rule that fired, for the journal")
    reference_price: Decimal
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    suggested_quantity: int | None = None

    _utc_ts = field_validator("ts", mode="before")(lambda v: ensure_utc(v))


class OrderIntent(BaseModel):
    """A signal after the risk engine sized and approved it. Still not an order."""

    model_config = ConfigDict(frozen=True)

    intent_id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    strategy_version_id: int
    account_id: int
    mode: TradingMode
    instrument_id: int
    side: OrderSide
    order_type: OrderType
    product: ProductType
    quantity: int = Field(gt=0)
    limit_price: Decimal | None = None
    trigger_price: Decimal | None = None
    idempotency_key: str = Field(description="strategy_version_id:signal_id")

    @classmethod
    def make_key(cls, strategy_version_id: int, signal_id: UUID) -> str:
        return f"{strategy_version_id}:{signal_id}"


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    fill_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    ts: datetime
    quantity: int = Field(gt=0)
    price: Decimal
    costs: Decimal = Decimal("0")
    is_partial: bool = False

    _utc_ts = field_validator("ts", mode="before")(lambda v: ensure_utc(v))


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: int
    mode: TradingMode
    instrument_id: int
    strategy_version_id: int | None = None
    quantity: int = Field(description="Signed: >0 long, <0 short, 0 flat")
    avg_price: Decimal
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    last_price: Decimal | None = None

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0
