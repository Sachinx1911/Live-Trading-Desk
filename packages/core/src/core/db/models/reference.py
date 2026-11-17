"""Reference data: exchanges, markets, segments, calendars, providers, brokers, costs
(ADR-006, ADR-011, ADR-012)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin
from core.db.models._enums import (
    AuthType,
    BrokerSessionStatus,
    ChargeSide,
    ChargeType,
    CostProduct,
    RateType,
    SessionType,
    pg_enum,
)


class Exchange(Base):
    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    session_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Market(Base):
    __tablename__ = "markets"
    __table_args__ = (UniqueConstraint("exchange_id", "code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (UniqueConstraint("market_id", "code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("markets.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    settlement: Mapped[str] = mapped_column(Text, nullable=False, default="T+1")


class TradingCalendar(Base):
    __tablename__ = "trading_calendars"
    __table_args__ = (PrimaryKeyConstraint("exchange_id", "date"),)

    exchange_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    session_type: Mapped[SessionType] = mapped_column(
        pg_enum(SessionType, "session_type"), nullable=False
    )
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataProvider(Base):
    __tablename__ = "data_providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    supports_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_trading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_type: Mapped[AuthType] = mapped_column(pg_enum(AuthType, "auth_type"), nullable=False)


class BrokerAccount(TimestampMixin, Base):
    """Credentials are encrypted with SECRETS_KEY before they reach this table."""

    __tablename__ = "broker_accounts"
    __table_args__ = (UniqueConstraint("user_id", "broker_id", "client_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("brokers.id", ondelete="RESTRICT"), nullable=False
    )
    client_code: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BrokerSession(Base):
    __tablename__ = "broker_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    broker_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("broker_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[BrokerSessionStatus] = mapped_column(
        pg_enum(BrokerSessionStatus, "broker_session_status"), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CostSchedule(Base):
    """Transaction cost rates with effective date ranges (ADR-011)."""

    __tablename__ = "cost_schedules"
    __table_args__ = (
        Index(
            "ix_cost_schedules_lookup",
            "exchange_id",
            "segment_id",
            "product",
            "charge_type",
            "effective_from",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="effective_range"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False
    )
    product: Mapped[CostProduct] = mapped_column(
        pg_enum(CostProduct, "cost_product"), nullable=False
    )
    charge_type: Mapped[ChargeType] = mapped_column(
        pg_enum(ChargeType, "charge_type"), nullable=False
    )
    side: Mapped[ChargeSide] = mapped_column(pg_enum(ChargeSide, "charge_side"), nullable=False)
    rate_type: Mapped[RateType] = mapped_column(pg_enum(RateType, "rate_type"), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
