"""option strike series: per-strike OI and Greeks derived from chain snapshots (Mark 1 1.1)

Derived data: rebuildable from `option_chain_snapshots` at any time
(`market_data.strike_series.rebuild_strike_series`), so rows may be replaced on rebuild.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    greek = sa.Numeric(18, 6)
    op.create_table(
        "option_strike_series",
        sa.Column("underlying_instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strike", sa.Numeric(14, 4), nullable=False),
        sa.Column("option_type", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("oi", sa.BigInteger(), nullable=True),
        sa.Column("oi_change_from_open", sa.BigInteger(), nullable=True),
        sa.Column("ltp", sa.Numeric(14, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("iv", greek, nullable=True),
        sa.Column("delta", greek, nullable=True),
        sa.Column("gamma", greek, nullable=True),
        sa.Column("theta", greek, nullable=True),
        sa.Column("vega", greek, nullable=True),
        sa.CheckConstraint(
            "option_type IN ('CE', 'PE')", name=op.f("ck_option_strike_series_option_type")
        ),
        sa.ForeignKeyConstraint(
            ["underlying_instrument_id"],
            ["instruments.id"],
            name=op.f("fk_option_strike_series_underlying_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_option_strike_series_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "underlying_instrument_id",
            "expiry",
            "strike",
            "option_type",
            "ts",
            "provider_id",
            name=op.f("pk_option_strike_series"),
        ),
    )
    op.execute(
        "SELECT create_hypertable('option_strike_series', 'ts', "
        "chunk_time_interval => INTERVAL '7 days')"
    )
    op.execute(
        "ALTER TABLE option_strike_series SET (timescaledb.compress, "
        "timescaledb.compress_segmentby = 'underlying_instrument_id,expiry,option_type', "
        "timescaledb.compress_orderby = 'strike,ts')"
    )
    op.execute("SELECT add_compression_policy('option_strike_series', INTERVAL '30 days')")


def downgrade() -> None:
    op.drop_table("option_strike_series")
