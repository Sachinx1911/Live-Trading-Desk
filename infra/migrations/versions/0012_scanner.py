"""scanner: scan_snapshots and saved_scans (Market Scanner)

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "scan_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("instrument_count", sa.Integer(), nullable=False),
        sa.Column("rows", jsonb, nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_scan_snapshots_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_snapshots")),
        sa.UniqueConstraint(
            "provider_id", "as_of_date", name=op.f("uq_scan_snapshots_provider_id")
        ),
    )
    op.create_table(
        "saved_scans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("filters", jsonb, nullable=False),
        sa.Column("columns", jsonb, nullable=False),
        sa.Column("sort", jsonb, nullable=True),
        sa.Column("is_preset", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_saved_scans_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_scans")),
    )
    op.create_index("ix_saved_scans_user_id", "saved_scans", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_scans_user_id", table_name="saved_scans")
    op.drop_table("saved_scans")
    op.drop_table("scan_snapshots")
