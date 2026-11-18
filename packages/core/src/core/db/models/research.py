"""Phase 4 research tables: backtest jobs/results/trades, optimisation (grid, random,
walk-forward) and replay sessions. Results are immutable once a job has succeeded; the
frozen `config` + `config_hash` + `data_hash` make every run reproducible (ADR-002)."""

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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base
from core.db.models._enums import JobStatus, OptimizationKind, ReplayStatus, pg_enum
from core.models.enums import OrderSide, Timeframe

MONEY = Numeric(18, 2)
PRICE = Numeric(14, 4)


class BacktestJob(Base):
    __tablename__ = "backtest_jobs"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="range_order"),
        CheckConstraint("progress_pct >= 0 AND progress_pct <= 100", name="progress_range"),
        Index("ix_backtest_jobs_version_status", "strategy_version_id", "status"),
        Index("ix_backtest_jobs_config_hash", "config_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum(Timeframe, "timeframe"), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    progress_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("backtest_jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    equity_curve: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    drawdown_curve: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    monthly_table: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    data_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    elapsed_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    regime_table: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_backtest_trades_result_entry", "result_id", "entry_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("backtest_results.id", ondelete="CASCADE"), nullable=False
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
    costs: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    net_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bars_held: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mae: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    mfe: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    regime: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class OptimizationJob(Base):
    __tablename__ = "optimization_jobs"
    __table_args__ = (
        CheckConstraint("progress_pct >= 0 AND progress_pct <= 100", name="progress_range"),
        Index("ix_optimization_jobs_version_status", "strategy_version_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[OptimizationKind] = mapped_column(
        pg_enum(OptimizationKind, "optimization_kind"), nullable=False
    )
    param_space: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="sharpe")
    windows: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    progress_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_backtest_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("backtest_jobs.id", ondelete="SET NULL"), nullable=True
    )


class OptimizationResult(Base):
    __tablename__ = "optimization_results"
    __table_args__ = (Index("ix_optimization_results_job_rank", "job_id", "rank"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("optimization_jobs.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    window: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_oos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReplaySession(Base):
    __tablename__ = "replay_sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    timeframe: Mapped[Timeframe] = mapped_column(pg_enum(Timeframe, "timeframe"), nullable=False)
    strategy_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ReplayStatus] = mapped_column(
        pg_enum(ReplayStatus, "replay_status"), nullable=False, default=ReplayStatus.CREATED
    )
    speed: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=1)
    cursor_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
