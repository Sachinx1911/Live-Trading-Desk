"""ai: strategy_nl_drafts — natural-language builder drafts and clarification threads (Phase 5)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18 08:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_VALUES = ("draft", "saved", "discarded")


def upgrade() -> None:
    status = postgresql.ENUM(*STATUS_VALUES, name="nl_draft_status")
    status.create(op.get_bind(), checkfirst=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "strategy_nl_drafts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("draft_id", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(*STATUS_VALUES, name="nl_draft_status", create_type=False),
            nullable=False,
        ),
        sa.Column("request", jsonb, nullable=False),
        sa.Column("extraction", jsonb, nullable=False),
        sa.Column("dsl", jsonb, nullable=False),
        sa.Column("validation", jsonb, nullable=False),
        sa.Column("missing_information", jsonb, nullable=False),
        sa.Column("questions", jsonb, nullable=False),
        sa.Column("defaults_applied", jsonb, nullable=False),
        sa.Column("unsupported", jsonb, nullable=False),
        sa.Column("changes", jsonb, nullable=False),
        sa.Column("thread", jsonb, nullable=False),
        sa.Column("ai_call_ids", jsonb, nullable=False),
        sa.Column("strategy_version_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
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
            ["strategy_version_id"],
            ["strategy_versions.id"],
            name=op.f("fk_strategy_nl_drafts_strategy_version_id_strategy_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_strategy_nl_drafts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_nl_drafts")),
        sa.UniqueConstraint("draft_id", name=op.f("uq_strategy_nl_drafts_draft_id")),
    )
    op.create_index(
        op.f("ix_strategy_nl_drafts_user_id"), "strategy_nl_drafts", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_nl_drafts_user_id"), table_name="strategy_nl_drafts")
    op.drop_table("strategy_nl_drafts")
    op.execute("DROP TYPE IF EXISTS nl_draft_status")
