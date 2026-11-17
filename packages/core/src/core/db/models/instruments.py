"""Instruments, provider mappings, point-in-time history, F&O contracts, corporate actions,
events (ADR-011, ADR-013)."""

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
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin
from core.db.models._enums import (
    ContractType,
    CorporateActionType,
    EventType,
    HistoryAttribute,
    Impact,
    InstrumentType,
    Settlement,
    pg_enum,
)
from core.models.enums import OptionType


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange_id", "symbol"),
        CheckConstraint("lot_size > 0", name="lot_size_positive"),
        CheckConstraint("tick_size > 0", name="tick_size_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exchanges.id", ondelete="RESTRICT"), nullable=False
    )
    segment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("segments.id", ondelete="RESTRICT"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    exchange_token: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        pg_enum(InstrumentType, "instrument_type"), nullable=False
    )
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0.05")
    )
    freeze_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_tradable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    listed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    delisted_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class InstrumentMapping(Base):
    __tablename__ = "instrument_mappings"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_token", "valid_from"),
        Index("ix_instrument_mappings_instrument_provider", "instrument_id", "provider_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_providers.id", ondelete="CASCADE"), nullable=False
    )
    provider_symbol: Mapped[str] = mapped_column(Text, nullable=False)
    provider_token: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class InstrumentHistory(Base):
    __tablename__ = "instrument_history"
    __table_args__ = (
        Index("ix_instrument_history_lookup", "instrument_id", "attribute", "effective_from"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    attribute: Mapped[HistoryAttribute] = mapped_column(
        pg_enum(HistoryAttribute, "history_attribute"), nullable=False
    )
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        Index("ix_contracts_underlying_expiry", "underlying_id", "expiry"),
        CheckConstraint(
            "(contract_type = 'future' AND strike IS NULL AND option_type IS NULL) OR "
            "(contract_type = 'option' AND strike IS NOT NULL AND option_type IS NOT NULL)",
            name="option_fields_consistent",
        ),
    )

    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    underlying_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    option_type: Mapped[OptionType | None] = mapped_column(
        pg_enum(OptionType, "option_type"), nullable=True
    )
    contract_type: Mapped[ContractType] = mapped_column(
        pg_enum(ContractType, "contract_type"), nullable=False
    )
    settlement: Mapped[Settlement] = mapped_column(
        pg_enum(Settlement, "settlement"), nullable=False
    )
    multiplier: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal(1))


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (Index("ix_corporate_actions_instrument_ex", "instrument_id", "ex_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[CorporateActionType] = mapped_column(
        pg_enum(CorporateActionType, "corporate_action_type"), nullable=False
    )
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ratio_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ratio_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    adjustment_factor: Mapped[Decimal | None] = mapped_column(Numeric(18, 10), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Event(Base):
    """Scheduled market events; `blocks_trading` is consumed by the risk engine."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_starts_at", "starts_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    instrument_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=True
    )
    impact: Mapped[Impact] = mapped_column(pg_enum(Impact, "impact"), nullable=False)
    blocks_trading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
