"""Strategy skeleton: strategies, immutable versions, denormalised conditions, approvals,
activations (ADR-003, ADR-008, ADR-009)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin
from core.db.models._enums import (
    ActivationStatus,
    ConditionRole,
    CreatedBy,
    Decision,
    StrategyCategory,
    StrategyOrigin,
    StrategyVersionStatus,
    pg_enum,
)
from core.models.enums import TradingMode


class Strategy(TimestampMixin, Base):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[StrategyCategory] = mapped_column(
        pg_enum(StrategyCategory, "strategy_category"), nullable=False
    )
    origin: Mapped[StrategyOrigin] = mapped_column(
        pg_enum(StrategyOrigin, "strategy_origin"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StrategyVersion(Base):
    """Immutable once status leaves `draft`: a DB trigger (migration 0004) rejects any
    change to dsl / dsl_hash / dsl_schema_version / source_text on non-draft rows."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_no", name="uq_strategy_versions_version_no"),
        UniqueConstraint("strategy_id", "dsl_hash", name="uq_strategy_versions_dsl_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[StrategyVersionStatus] = mapped_column(
        pg_enum(StrategyVersionStatus, "strategy_version_status"),
        nullable=False,
        default=StrategyVersionStatus.DRAFT,
    )
    dsl: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dsl_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    dsl_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[CreatedBy] = mapped_column(pg_enum(CreatedBy, "created_by"), nullable=False)
    ai_call_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_calls.id", ondelete="SET NULL"), nullable=True
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StrategyCondition(Base):
    """Denormalised from `dsl` for library search; always rebuildable."""

    __tablename__ = "strategy_conditions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ConditionRole] = mapped_column(
        pg_enum(ConditionRole, "condition_role"), nullable=False
    )
    indicator: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class StrategyApproval(Base):
    __tablename__ = "strategy_approvals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    from_status: Mapped[StrategyVersionStatus] = mapped_column(
        pg_enum(StrategyVersionStatus, "strategy_version_status"), nullable=False
    )
    to_status: Mapped[StrategyVersionStatus] = mapped_column(
        pg_enum(StrategyVersionStatus, "strategy_version_status"), nullable=False
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    decision: Mapped[Decision] = mapped_column(pg_enum(Decision, "decision"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StrategyActivation(Base):
    """Binds one version to exactly one trading mode and one account (ADR-008).
    paper_account_id / live_account_id reference the Phase 3 account tables (migration 0007)."""

    __tablename__ = "strategy_activations"
    __table_args__ = (
        CheckConstraint(
            "(trading_mode = 'paper' AND paper_account_id IS NOT NULL "
            "AND live_account_id IS NULL) OR "
            "(trading_mode = 'live' AND live_account_id IS NOT NULL "
            "AND paper_account_id IS NULL)",
            name="exactly_one_account",
        ),
        CheckConstraint(
            "trading_mode <> 'live' OR activated_by IS NOT NULL", name="live_requires_user"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    trading_mode: Mapped[TradingMode] = mapped_column(
        pg_enum(TradingMode, "trading_mode"), nullable=False
    )
    paper_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("paper_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    live_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("live_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    params_override: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ActivationStatus] = mapped_column(
        pg_enum(ActivationStatus, "activation_status"), nullable=False
    )
    activated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
