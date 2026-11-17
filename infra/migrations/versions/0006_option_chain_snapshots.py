"""option chain snapshots hypertable (ADR-010)

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_chain_snapshots",
        sa.Column("underlying_instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("underlying_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["underlying_instrument_id"],
            ["instruments.id"],
            name=op.f("fk_option_chain_snapshots_underlying_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_option_chain_snapshots_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "underlying_instrument_id",
            "expiry",
            "ts",
            "provider_id",
            name=op.f("pk_option_chain_snapshots"),
        ),
    )
    op.execute(
        "SELECT create_hypertable('option_chain_snapshots', 'ts', "
        "chunk_time_interval => INTERVAL '7 days')"
    )
    op.execute(
        "ALTER TABLE option_chain_snapshots SET (timescaledb.compress, "
        "timescaledb.compress_segmentby = 'underlying_instrument_id,expiry', "
        "timescaledb.compress_orderby = 'ts')"
    )
    op.execute("SELECT add_compression_policy('option_chain_snapshots', INTERVAL '30 days')")


def downgrade() -> None:
    op.drop_table("option_chain_snapshots")
