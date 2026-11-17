"""strategy skeleton with version immutability trigger

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "trend",
                "mean_reversion",
                "breakout",
                "options",
                "swing",
                "other",
                name="strategy_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum(
                "user_nl",
                "user_visual",
                "ai_research",
                "ai_learning",
                "import",
                name="strategy_origin",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
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
            ["user_id"], ["users.id"], name=op.f("fk_strategies_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategies")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_strategies_user_id")),
    )
    op.create_index(op.f("ix_strategies_user_id"), "strategies", ["user_id"], unique=False)
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("strategy_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "backtested",
                "validated",
                "paper",
                "approved_live",
                "retired",
                "rejected",
                name="strategy_version_status",
            ),
            nullable=False,
        ),
        sa.Column("dsl", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dsl_schema_version", sa.Text(), nullable=False),
        sa.Column("dsl_hash", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_language", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Enum("user", "ai", name="created_by"), nullable=False),
        sa.Column("ai_call_id", sa.BigInteger(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["strategy_versions.id"],
            name=op.f("fk_strategy_versions_parent_version_id_strategy_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_strategy_versions_strategy_id_strategies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_versions")),
        sa.UniqueConstraint("strategy_id", "dsl_hash", name="uq_strategy_versions_dsl_hash"),
        sa.UniqueConstraint("strategy_id", "version_no", name="uq_strategy_versions_version_no"),
    )
    op.create_table(
        "strategy_conditions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("entry", "exit", "stop", "target", "filter", name="condition_role"),
            nullable=False,
        ),
        sa.Column("indicator", sa.Text(), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("operator", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["strategy_versions.id"],
            name=op.f("fk_strategy_conditions_version_id_strategy_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_conditions")),
    )
    op.create_index(
        op.f("ix_strategy_conditions_version_id"),
        "strategy_conditions",
        ["version_id"],
        unique=False,
    )
    op.create_table(
        "strategy_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "draft",
                "backtested",
                "validated",
                "paper",
                "approved_live",
                "retired",
                "rejected",
                name="strategy_version_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "draft",
                "backtested",
                "validated",
                "paper",
                "approved_live",
                "retired",
                "rejected",
                name="strategy_version_status",
            ),
            nullable=False,
        ),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision", sa.Enum("approved", "rejected", name="decision"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_strategy_approvals_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["strategy_versions.id"],
            name=op.f("fk_strategy_approvals_version_id_strategy_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_approvals")),
    )
    op.create_index(
        op.f("ix_strategy_approvals_version_id"), "strategy_approvals", ["version_id"], unique=False
    )
    op.create_table(
        "strategy_activations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("trading_mode", sa.Enum("paper", "live", name="trading_mode"), nullable=False),
        sa.Column("paper_account_id", sa.BigInteger(), nullable=True),
        sa.Column("live_account_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("params_override", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "paused", "stopped", name="activation_status"),
            nullable=False,
        ),
        sa.Column("activated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(trading_mode = 'paper' AND paper_account_id IS NOT NULL "
            "AND live_account_id IS NULL) OR "
            "(trading_mode = 'live' AND live_account_id IS NOT NULL "
            "AND paper_account_id IS NULL)",
            name=op.f("ck_strategy_activations_exactly_one_account"),
        ),
        sa.CheckConstraint(
            "trading_mode <> 'live' OR activated_by IS NOT NULL",
            name=op.f("ck_strategy_activations_live_requires_user"),
        ),
        sa.ForeignKeyConstraint(
            ["activated_by"],
            ["users.id"],
            name=op.f("fk_strategy_activations_activated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_strategy_activations_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["strategy_versions.id"],
            name=op.f("fk_strategy_activations_version_id_strategy_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_activations")),
    )
    op.create_index(
        op.f("ix_strategy_activations_version_id"),
        "strategy_activations",
        ["version_id"],
        unique=False,
    )

    # --- immutability (ADR-003 / ADR-009): content of a non-draft version never changes --
    op.execute(
        """
        CREATE OR REPLACE FUNCTION strategy_versions_guard_immutable() RETURNS trigger AS $$
        BEGIN
            IF OLD.status <> 'draft' AND (
                NEW.dsl IS DISTINCT FROM OLD.dsl
                OR NEW.dsl_hash IS DISTINCT FROM OLD.dsl_hash
                OR NEW.dsl_schema_version IS DISTINCT FROM OLD.dsl_schema_version
                OR NEW.source_text IS DISTINCT FROM OLD.source_text
                OR NEW.strategy_id IS DISTINCT FROM OLD.strategy_id
                OR NEW.version_no IS DISTINCT FROM OLD.version_no
            ) THEN
                RAISE EXCEPTION
                    'strategy_versions % is % and immutable; create a new draft version',
                    OLD.id, OLD.status USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.status = 'draft' AND NEW.status <> 'draft' AND NEW.frozen_at IS NULL THEN
                NEW.frozen_at := now();
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_strategy_versions_immutable
        BEFORE UPDATE ON strategy_versions
        FOR EACH ROW EXECUTE FUNCTION strategy_versions_guard_immutable()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_strategy_versions_immutable ON strategy_versions")
    op.execute("DROP FUNCTION IF EXISTS strategy_versions_guard_immutable()")

    op.drop_table("strategy_activations")
    op.drop_table("strategy_approvals")
    op.drop_table("strategy_conditions")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
    op.execute("DROP TYPE IF EXISTS strategy_category")
    op.execute("DROP TYPE IF EXISTS strategy_origin")
    op.execute("DROP TYPE IF EXISTS strategy_version_status")
    op.execute("DROP TYPE IF EXISTS created_by")
    op.execute("DROP TYPE IF EXISTS condition_role")
    op.execute("DROP TYPE IF EXISTS decision")
    op.execute("DROP TYPE IF EXISTS trading_mode")
    op.execute("DROP TYPE IF EXISTS activation_status")
