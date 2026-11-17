"""Market data core: historical candles and quote snapshots (Timescale hypertables),
import jobs and quality checks (ADR-004, ADR-006, ADR-010)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base
from core.db.models._enums import (
    ImportSourceType,
    JobStatus,
    QualityCheckType,
    QuoteFreshness,
    Severity,
    pg_enum,
)
from core.models.enums import Timeframe


class HistoricalCandle(Base):
    """Hypertable on `ts` (bar open, UTC). Raw, append-only; one row per provider."""

    __tablename__ = "historical_candles"
    __table_args__ = (
        PrimaryKeyConstraint("instrument_id", "timeframe", "ts", "provider_id"),
        CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ohlc_consistent",
        ),
        CheckConstraint("volume >= 0", name="volume_non_negative"),
    )

    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum(Timeframe, "timeframe"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_providers.id", ondelete="RESTRICT"), nullable=False
    )
    open: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    oi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    import_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("data_import_jobs.id", ondelete="SET NULL"), nullable=True
    )


class MarketQuote(Base):
    """Hypertable on `ts`; periodic last-quote snapshots. Short retention (ADR-010)."""

    __tablename__ = "market_quotes"
    __table_args__ = (PrimaryKeyConstraint("instrument_id", "ts", "provider_id"),)

    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_providers.id", ondelete="RESTRICT"), nullable=False
    )
    ltp: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    bid_px: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    ask_px: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    bid_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ask_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    oi: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    freshness: Mapped[QuoteFreshness] = mapped_column(
        pg_enum(QuoteFreshness, "quote_freshness"), nullable=False
    )


class DataImportJob(Base):
    __tablename__ = "data_import_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_providers.id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[ImportSourceType] = mapped_column(
        pg_enum(ImportSourceType, "import_source_type"), nullable=False
    )
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    instrument_scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    timeframe: Mapped[Timeframe | None] = mapped_column(
        pg_enum(Timeframe, "timeframe"), nullable=True
    )
    range_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    range_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[JobStatus] = mapped_column(pg_enum(JobStatus, "job_status"), nullable=False)
    rows_read: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rows_written: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rows_rejected: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"
    __table_args__ = (Index("ix_data_quality_checks_instrument_tf", "instrument_id", "timeframe"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("data_import_jobs.id", ondelete="CASCADE"), nullable=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum(Timeframe, "timeframe"), nullable=False)
    check_type: Mapped[QualityCheckType] = mapped_column(
        pg_enum(QualityCheckType, "quality_check_type"), nullable=False
    )
    range_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    range_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    severity: Mapped[Severity] = mapped_column(pg_enum(Severity, "severity"), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
