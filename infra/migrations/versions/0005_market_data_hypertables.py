"""market data core: candles and quotes as Timescale hypertables

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_import_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "api", "csv", "excel", "json", "parquet", "collector", name="import_source_type"
            ),
            nullable=False,
        ),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("instrument_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "timeframe",
            sa.Enum(
                "tick", "1s", "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M", name="timeframe"
            ),
            nullable=True,
        ),
        sa.Column("range_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("range_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                "partial",
                name="job_status",
            ),
            nullable=False,
        ),
        sa.Column("rows_read", sa.BigInteger(), nullable=False),
        sa.Column("rows_written", sa.BigInteger(), nullable=False),
        sa.Column("rows_rejected", sa.BigInteger(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_data_import_jobs_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_data_import_jobs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_import_jobs")),
        sa.UniqueConstraint("manifest_hash", name=op.f("uq_data_import_jobs_manifest_hash")),
    )
    op.create_table(
        "historical_candles",
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "timeframe",
            sa.Enum(
                "tick", "1s", "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M", name="timeframe"
            ),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("open", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("high", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("low", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("close", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("oi", sa.BigInteger(), nullable=True),
        sa.Column("provider_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("import_job_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name=op.f("ck_historical_candles_ohlc_consistent"),
        ),
        sa.CheckConstraint("volume >= 0", name=op.f("ck_historical_candles_volume_non_negative")),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["data_import_jobs.id"],
            name=op.f("fk_historical_candles_import_job_id_data_import_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_historical_candles_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_historical_candles_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "instrument_id", "timeframe", "ts", "provider_id", name=op.f("pk_historical_candles")
        ),
    )
    op.create_table(
        "market_quotes",
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("ltp", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("bid_px", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("ask_px", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("bid_qty", sa.Integer(), nullable=True),
        sa.Column("ask_qty", sa.Integer(), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("oi", sa.BigInteger(), nullable=True),
        sa.Column("provider_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "freshness", sa.Enum("live", "delayed", "stale", name="quote_freshness"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_market_quotes_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_market_quotes_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "instrument_id", "ts", "provider_id", name=op.f("pk_market_quotes")
        ),
    )
    op.create_table(
        "data_quality_checks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "timeframe",
            sa.Enum(
                "tick", "1s", "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M", name="timeframe"
            ),
            nullable=False,
        ),
        sa.Column(
            "check_type",
            sa.Enum(
                "missing_candles",
                "duplicates",
                "ohlc_invalid",
                "volume_spike",
                "gap_vs_prev_close",
                "stale_feed",
                name="quality_check_type",
            ),
            nullable=False,
        ),
        sa.Column("range_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("range_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("severity", sa.Enum("info", "warn", "error", name="severity"), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            ["data_import_jobs.id"],
            name=op.f("fk_data_quality_checks_import_job_id_data_import_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_data_quality_checks_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_checks")),
    )
    op.create_index(
        "ix_data_quality_checks_instrument_tf",
        "data_quality_checks",
        ["instrument_id", "timeframe"],
        unique=False,
    )

    # --- Timescale hypertables, compression and retention (ADR-004, ADR-010) -----------
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute(
        "SELECT create_hypertable('historical_candles', 'ts', "
        "chunk_time_interval => INTERVAL '7 days')"
    )
    op.execute(
        "ALTER TABLE historical_candles SET (timescaledb.compress, "
        "timescaledb.compress_segmentby = 'instrument_id, timeframe', "
        "timescaledb.compress_orderby = 'ts')"
    )
    op.execute("SELECT add_compression_policy('historical_candles', INTERVAL '30 days')")
    op.execute(
        "SELECT create_hypertable('market_quotes', 'ts', chunk_time_interval => INTERVAL '1 day')"
    )
    op.execute("SELECT add_retention_policy('market_quotes', INTERVAL '7 days')")


def downgrade() -> None:
    op.drop_table("data_quality_checks")
    op.drop_table("market_quotes")
    op.drop_table("historical_candles")
    op.drop_table("data_import_jobs")
    op.execute("DROP TYPE IF EXISTS import_source_type")
    op.execute("DROP TYPE IF EXISTS timeframe")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS quote_freshness")
    op.execute("DROP TYPE IF EXISTS quality_check_type")
    op.execute("DROP TYPE IF EXISTS severity")
