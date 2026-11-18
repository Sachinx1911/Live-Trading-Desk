"""Market regime storage (master prompt Module 6): one daily row per instrument, intraday
day-type rows every 15 minutes. Deterministic outputs of `strategy.regime`."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base
from core.db.models._enums import (
    RegimeDayType,
    RegimeStrength,
    RegimeStructure,
    RegimeTrend,
    RegimeVolatility,
    pg_enum,
)


class RegimeDaily(Base):
    __tablename__ = "regime_daily"
    __table_args__ = (
        PrimaryKeyConstraint("instrument_id", "date"),
        Index("ix_regime_daily_date", "date"),
    )

    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    trend: Mapped[RegimeTrend] = mapped_column(pg_enum(RegimeTrend, "regime_trend"), nullable=False)
    strength: Mapped[RegimeStrength] = mapped_column(
        pg_enum(RegimeStrength, "regime_strength"), nullable=False
    )
    volatility: Mapped[RegimeVolatility] = mapped_column(
        pg_enum(RegimeVolatility, "regime_volatility"), nullable=False
    )
    structure: Mapped[RegimeStructure] = mapped_column(
        pg_enum(RegimeStructure, "regime_structure"), nullable=False
    )
    adx: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    ema20: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ema50: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ema200: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    atr_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    vix: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    vix_percentile: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    event_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    events: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RegimeIntraday(Base):
    __tablename__ = "regime_intraday"
    __table_args__ = (PrimaryKeyConstraint("instrument_id", "ts"),)

    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    day_type: Mapped[RegimeDayType] = mapped_column(
        pg_enum(RegimeDayType, "regime_day_type"), nullable=False
    )
    or_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    or_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    vwap_distance_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    atr_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
