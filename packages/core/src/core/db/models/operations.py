"""Mark 1 Stage 3 storage (docs/mark-1-build-plan.md §3): trading protocols and their runs,
proactive alerts, raw news headlines, daily market breadth and stored daily reports.

Status-like columns are Text with CHECK constraints (no Postgres enum types), so the set can
grow by migration without enum surgery.
"""

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin

PROTOCOL_RUN_STATUSES = (
    "running",
    "awaiting_confirmation",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
)
ALERT_SEVERITIES = ("info", "warning", "critical")


class Protocol(TimestampMixin, Base):
    """A named, versioned list of tool calls (JSON only, no code; CLAUDE.md rule 4).

    `steps` = [{"tool": str, "args": {...}, "on_error": "stop" | "continue"}];
    editing a protocol bumps `version`; runs record the version they executed."""

    __tablename__ = "protocols"
    __table_args__ = (UniqueConstraint("code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False, server_default="trading")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    layout: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confirm_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )


class ProtocolRun(Base):
    """One execution of a protocol. Step results are appended as the run progresses."""

    __tablename__ = "protocol_runs"
    __table_args__ = (
        CheckConstraint("status IN ('" + "', '".join(PROTOCOL_RUN_STATUSES) + "')", name="status"),
        Index("ix_protocol_runs_protocol_started", "protocol_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    protocol_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    protocol_version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    trigger: Mapped[str] = mapped_column(Text, nullable=False)  # button | api | schedule | jarvis
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    """A proactive notice (EDITH without AI). `dedup_key` suppresses repeats within a window."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('" + "', '".join(ALERT_SEVERITIES) + "')", name="severity"),
        Index("ix_alerts_ts", "ts"),
        Index("ix_alerts_dedup_key_ts", "dedup_key", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    instrument_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True
    )
    delivered: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NewsItem(Base):
    """Raw headline from an RSS feed (append-only). Title, link, feed summary only."""

    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("url"), Index("ix_news_items_published_at", "published_at"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestError(Base):
    """A failed feed fetch, kept so dead feeds are visible."""

    __tablename__ = "ingest_errors"
    __table_args__ = (Index("ix_ingest_errors_ts", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    feed_url: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    error: Mapped[str] = mapped_column(Text, nullable=False)


class MarketBreadth(Base):
    """Derived daily breadth for a universe (rebuildable from stored daily candles)."""

    __tablename__ = "market_breadth"
    __table_args__ = (UniqueConstraint("as_of_date", "universe", "provider_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    universe: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_providers.id", ondelete="RESTRICT"), nullable=False
    )
    universe_size: Mapped[int] = mapped_column(Integer, nullable=False)
    advances: Mapped[int] = mapped_column(Integer, nullable=False)
    declines: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False)
    new_52w_high: Mapped[int] = mapped_column(Integer, nullable=False)
    new_52w_low: Mapped[int] = mapped_column(Integer, nullable=False)
    above_ema50_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    above_ema200_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    index_moves: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyReport(Base):
    """Stored end-of-day report / evening brief. `content` is the structured data the text
    was rendered from; regenerating a day replaces the row."""

    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("report_date", "kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # eod
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    text_md: Mapped[str] = mapped_column(Text, nullable=False)
    delivered: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
