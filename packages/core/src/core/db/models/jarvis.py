"""Mark 1 Stage 4 storage (docs/mark-1-build-plan.md §4.1, §4.6): the tool server's tokens and
authority log, and JARVIS's recorded market views with their scores.

`tool_calls` and `ai_observations` are append-only. `ai_view_scores` is derived from
`ai_observations` + stored candles and can be rebuilt. Observations are never read by any
strategy, risk check or order path (ADR-009); they measure JARVIS, nothing more.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base

TOOL_LEVELS = ("green", "yellow")  # red is never exposed to the tool server
TOOL_CALL_STATUSES = ("ok", "error", "refused")
VIEW_DIRECTIONS = ("up", "down", "sideways")
VIEW_OUTCOMES = ("hit", "miss", "void")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ('" + "', '".join(values) + "')"


class ToolToken(Base):
    """A service token for one tool-server client (e.g. one jarvis install). Only a SHA-256
    hash is stored; the token is shown once at creation."""

    __tablename__ = "tool_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        CheckConstraint(_in("max_level", TOOL_LEVELS), name="max_level"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    max_level: Mapped[str] = mapped_column(Text, nullable=False, server_default="green")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolCall(Base):
    """Authority log: every call the tool server received, allowed or refused."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint(_in("status", TOOL_CALL_STATUSES), name="status"),
        Index("ix_tool_calls_ts", "ts"),
        Index("ix_tool_calls_tool_ts", "tool", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    token_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tool_tokens.id", ondelete="SET NULL"), nullable=True
    )
    transport: Mapped[str] = mapped_column(Text, nullable=False)  # http | mcp
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AiObservation(Base):
    """A directional view JARVIS stated, with the reference price the tool server took at that
    moment. Append-only."""

    __tablename__ = "ai_observations"
    __table_args__ = (
        CheckConstraint(_in("direction", VIEW_DIRECTIONS), name="direction"),
        CheckConstraint("horizon_days >= 1 AND horizon_days <= 250", name="horizon_days"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        Index("ix_ai_observations_ts", "ts"),
        Index("ix_ai_observations_instrument_id", "instrument_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    caller: Mapped[str] = mapped_column(Text, nullable=False)  # jarvis | brief | ...
    mode: Mapped[str | None] = mapped_column(Text, nullable=True)  # jarvis | friday | karen
    instrument_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    invalidation: Mapped[str | None] = mapped_column(Text, nullable=True)
    invalidation_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    ref_source: Mapped[str] = mapped_column(Text, nullable=False)
    ref_freshness: Mapped[str] = mapped_column(Text, nullable=False)
    ref_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tool_call_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tool_calls.id", ondelete="SET NULL"), nullable=True
    )


class AiViewScore(Base):
    """Derived grade of one matured observation (rebuildable from observations + candles)."""

    __tablename__ = "ai_view_scores"
    __table_args__ = (
        UniqueConstraint("observation_id"),
        CheckConstraint(_in("outcome", VIEW_OUTCOMES), name="outcome"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    observation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ai_observations.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    threshold_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
