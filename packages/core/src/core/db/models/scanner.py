"""Market scanner storage: nightly universe metric snapshots and saved/preset scans."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.base import Base, TimestampMixin


class ScanSnapshot(Base):
    """One row per provider x trading day: every tracked instrument's scanner metrics as a
    JSONB list. Rebuilt nightly; filtering happens in memory (Polars) on the latest row."""

    __tablename__ = "scan_snapshots"
    __table_args__ = (UniqueConstraint("provider_id", "as_of_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("data_providers.id", ondelete="RESTRICT"), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    instrument_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)


class SavedScan(TimestampMixin, Base):
    """A filter + sort + column set. Presets have `is_preset=True` and no owner."""

    __tablename__ = "saved_scans"
    __table_args__ = (Index("ix_saved_scans_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sort: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
