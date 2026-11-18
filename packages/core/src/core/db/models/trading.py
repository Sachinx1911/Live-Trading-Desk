"""Phase 3 trading tables: paper and live accounts/orders/positions/trades (kept strictly
apart, ADR-008), reconciliation, kill switch, risk limits, journal and portfolio analytics.

Order status transitions are recorded append-only in the *_order_events tables; for live
orders the `source` column records who moved the state (broker callback, reconciliation,
user, gateway) and nothing else may (ADR-007)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin
from core.db.models._enums import (
    ActorType,
    KillSwitchAction,
    KillSwitchScope,
    OrderEventSource,
    ReconciliationAction,
    RiskLimitScope,
    pg_enum,
)
from core.models.enums import OrderSide, OrderStatus, OrderType, ProductType, TradingMode

MONEY = Numeric(18, 2)
PRICE = Numeric(14, 4)


# --- paper -------------------------------------------------------------------------------


class PaperAccount(TimestampMixin, Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (CheckConstraint("initial_capital > 0", name="initial_capital_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    initial_capital: Mapped[Decimal] = mapped_column(MONEY, nullable=False, server_default="100000")
    cash: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    equity_hwm: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        UniqueConstraint(
            "paper_account_id", "idempotency_key", name="uq_paper_orders_account_idempotency"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("filled_qty >= 0 AND filled_qty <= quantity", name="filled_within_qty"),
        Index("ix_paper_orders_account_status", "paper_account_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False
    )
    activation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    signal_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side"), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(pg_enum(OrderType, "order_type"), nullable=False)
    product: Mapped[ProductType] = mapped_column(
        pg_enum(ProductType, "product_type"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    costs: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    cost_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    bid_at_place: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    ask_at_place: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PaperOrderEvent(Base):
    """Append-only order state transitions."""

    __tablename__ = "paper_order_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False
    )
    fill_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fill_px: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="simulator")
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        Index(
            "uq_paper_positions_open",
            "paper_account_id",
            "instrument_id",
            "product",
            unique=True,
            postgresql_where="closed_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    product: Mapped[ProductType] = mapped_column(
        pg_enum(ProductType, "product_type"), nullable=False
    )
    activation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # signed
    avg_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    last_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperTrade(Base):
    """Closed round trips."""

    __tablename__ = "paper_trades"
    __table_args__ = (Index("ix_paper_trades_account_exit", "paper_account_id", "exit_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False
    )
    activation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True
    )
    strategy_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    exit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    gross_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    costs: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    regime: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    bars_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_adverse: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    max_favorable: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)


# --- live --------------------------------------------------------------------------------


class LiveAccount(TimestampMixin, Base):
    """Must be explicitly enabled by a user before the gateway will route to it."""

    __tablename__ = "live_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    enabled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LiveOrder(Base):
    __tablename__ = "live_orders"
    __table_args__ = (
        UniqueConstraint(
            "live_account_id", "idempotency_key", name="uq_live_orders_account_idempotency"
        ),
        UniqueConstraint(
            "live_account_id", "broker_order_id", name="uq_live_orders_account_broker"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("filled_qty >= 0 AND filled_qty <= quantity", name="filled_within_qty"),
        Index("ix_live_orders_account_status", "live_account_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    live_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("live_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    activation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    signal_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side"), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(pg_enum(OrderType, "order_type"), nullable=False)
    product: Mapped[ProductType] = mapped_column(
        pg_enum(ProductType, "product_type"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    filled_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    costs: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    gate_results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    broker_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LiveOrderEvent(Base):
    __tablename__ = "live_order_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("live_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"), nullable=False
    )
    fill_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fill_px: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[OrderEventSource] = mapped_column(
        pg_enum(OrderEventSource, "order_event_source"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LivePosition(Base):
    __tablename__ = "live_positions"
    __table_args__ = (
        Index(
            "uq_live_positions_open",
            "live_account_id",
            "instrument_id",
            "product",
            unique=True,
            postgresql_where="closed_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    live_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("live_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    product: Mapped[ProductType] = mapped_column(
        pg_enum(ProductType, "product_type"), nullable=False
    )
    activation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    last_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    broker_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    broker_avg_px: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LiveTrade(Base):
    __tablename__ = "live_trades"
    __table_args__ = (Index("ix_live_trades_account_exit", "live_account_id", "exit_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    live_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("live_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    activation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_activations.id", ondelete="SET NULL"), nullable=True
    )
    strategy_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    exit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    gross_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    costs: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    regime: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    bars_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_adverse: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    max_favorable: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    live_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("live_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    orders_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positions_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mismatches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    action_taken: Mapped[ReconciliationAction] = mapped_column(
        pg_enum(ReconciliationAction, "reconciliation_action"), nullable=False
    )


class KillSwitchEvent(Base):
    __tablename__ = "kill_switch_events"
    __table_args__ = (Index("ix_kill_switch_events_ts", "ts", postgresql_using="btree"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[KillSwitchScope] = mapped_column(
        pg_enum(KillSwitchScope, "kill_switch_scope"), nullable=False
    )
    scope_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[KillSwitchAction] = mapped_column(
        pg_enum(KillSwitchAction, "kill_switch_action"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[ActorType] = mapped_column(pg_enum(ActorType, "actor_type"), nullable=False)
    positions_flattened: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RiskLimit(Base):
    """Versioned limits per scope; changes insert a new row and deactivate the old one."""

    __tablename__ = "risk_limits"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "version"),
        Index(
            "uq_risk_limits_active",
            "scope",
            "scope_id",
            unique=True,
            postgresql_where="is_active",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[RiskLimitScope] = mapped_column(
        pg_enum(RiskLimitScope, "risk_limit_scope"), nullable=False
    )
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


# --- journal and analytics -------------------------------------------------------------


class JournalEntry(TimestampMixin, Base):
    __tablename__ = "journal_entries"
    __table_args__ = (Index("ix_journal_entries_trade_ref", "trade_ref_table", "trade_ref_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[TradingMode] = mapped_column(pg_enum(TradingMode, "trading_mode"), nullable=False)
    trade_ref_table: Mapped[str | None] = mapped_column(Text, nullable=True)
    trade_ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    strategy_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pnl: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    risk_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    ai_review_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("account_id", "mode", "ts"),
        Index("ix_portfolio_snapshots_user_ts", "user_id", "ts"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[TradingMode] = mapped_column(pg_enum(TradingMode, "trading_mode"), nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    exposure: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    realized_day: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    unrealized: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PerformanceDaily(Base):
    __tablename__ = "performance_daily"
    __table_args__ = (PrimaryKeyConstraint("account_id", "mode", "day"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[TradingMode] = mapped_column(pg_enum(TradingMode, "trading_mode"), nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fees: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    max_dd: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
