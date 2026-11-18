"""ai: ai_calls (ADR-009) and the strategy_versions.ai_call_id foreign key (Phase 5)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18 07:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_AGENT_VALUES = (
    "translator",
    "analyst",
    "researcher",
    "reviewer",
    "risk_reviewer",
    "monitor_explainer",
    "auditor",
)


def upgrade() -> None:
    ai_agent = postgresql.ENUM(*AI_AGENT_VALUES, name="ai_agent")
    ai_agent.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "agent",
            postgresql.ENUM(*AI_AGENT_VALUES, name="ai_agent", create_type=False),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column(
            "input_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("payload_uri", sa.Text(), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_calls_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_calls")),
    )
    op.create_index("ix_ai_calls_agent_ts", "ai_calls", ["agent", "ts"], unique=False)
    op.create_index("ix_ai_calls_job_id", "ai_calls", ["job_id"], unique=False)
    op.create_index("ix_ai_calls_ts", "ai_calls", ["ts"], unique=False)
    op.create_foreign_key(
        op.f("fk_strategy_versions_ai_call_id_ai_calls"),
        "strategy_versions",
        "ai_calls",
        ["ai_call_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_strategy_versions_ai_call_id_ai_calls"), "strategy_versions", type_="foreignkey"
    )
    op.drop_index("ix_ai_calls_ts", table_name="ai_calls")
    op.drop_index("ix_ai_calls_job_id", table_name="ai_calls")
    op.drop_index("ix_ai_calls_agent_ts", table_name="ai_calls")
    op.drop_table("ai_calls")
    op.execute("DROP TYPE IF EXISTS ai_agent")
