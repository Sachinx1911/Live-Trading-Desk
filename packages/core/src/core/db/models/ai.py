"""Phase 5-6 AI tables (ADR-009). `ai_calls` is the append-only record of every LLM call:
who asked (agent), with what (prompt + schema versions, input record ids), what it cost and
whether the answer validated. Prompts and raw responses live in object storage behind
`payload_uri`; the database holds the accounting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin, UserOwnedMixin
from core.db.models._enums import AiAgent, NlDraftStatus, pg_enum


class AiCall(Base):
    __tablename__ = "ai_calls"
    __table_args__ = (
        Index("ix_ai_calls_ts", "ts"),
        Index("ix_ai_calls_agent_ts", "agent", "ts"),
        Index("ix_ai_calls_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent: Mapped[AiAgent] = mapped_column(pg_enum(AiAgent, "ai_agent"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_name: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StrategyNlDraft(UserOwnedMixin, TimestampMixin, Base):
    """A natural-language strategy draft and its clarification thread (master prompt §7).
    Saving creates a strategy version from `dsl` and links it here; the draft itself is
    never a runnable strategy."""

    __tablename__ = "strategy_nl_drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[NlDraftStatus] = mapped_column(
        pg_enum(NlDraftStatus, "nl_draft_status"), nullable=False
    )
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dsl: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    defaults_applied: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    unsupported: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    changes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    thread: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    ai_call_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    strategy_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True
    )
