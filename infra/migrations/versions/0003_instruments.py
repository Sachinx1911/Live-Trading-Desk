"""instruments, mappings, history, contracts, corporate actions, events

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exchange_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("isin", sa.Text(), nullable=True),
        sa.Column("exchange_token", sa.Text(), nullable=True),
        sa.Column(
            "instrument_type",
            sa.Enum(
                "equity",
                "index",
                "future",
                "option",
                "etf",
                "currency",
                "commodity",
                name="instrument_type",
            ),
            nullable=False,
        ),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("freeze_qty", sa.Integer(), nullable=True),
        sa.Column("is_tradable", sa.Boolean(), nullable=False),
        sa.Column("listed_at", sa.Date(), nullable=True),
        sa.Column("delisted_at", sa.Date(), nullable=True),
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
        sa.CheckConstraint("lot_size > 0", name=op.f("ck_instruments_lot_size_positive")),
        sa.CheckConstraint("tick_size > 0", name=op.f("ck_instruments_tick_size_positive")),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name=op.f("fk_instruments_exchange_id_exchanges"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.id"],
            name=op.f("fk_instruments_segment_id_segments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
        sa.UniqueConstraint("exchange_id", "symbol", name=op.f("uq_instruments_exchange_id")),
    )
    op.create_index(
        op.f("ix_instruments_exchange_token"), "instruments", ["exchange_token"], unique=False
    )
    op.create_index(op.f("ix_instruments_isin"), "instruments", ["isin"], unique=False)
    op.create_table(
        "instrument_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_symbol", sa.Text(), nullable=False),
        sa.Column("provider_token", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_instrument_mappings_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_instrument_mappings_provider_id_data_providers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instrument_mappings")),
        sa.UniqueConstraint(
            "provider_id",
            "provider_token",
            "valid_from",
            name=op.f("uq_instrument_mappings_provider_id"),
        ),
    )
    op.create_index(
        "ix_instrument_mappings_instrument_provider",
        "instrument_mappings",
        ["instrument_id", "provider_id"],
        unique=False,
    )
    op.create_table(
        "instrument_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "attribute",
            sa.Enum(
                "lot_size", "tick_size", "symbol", "freeze_qty", "name", name="history_attribute"
            ),
            nullable=False,
        ),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_instrument_history_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instrument_history")),
    )
    op.create_index(
        "ix_instrument_history_lookup",
        "instrument_history",
        ["instrument_id", "attribute", "effective_from"],
        unique=False,
    )
    op.create_table(
        "contracts",
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("underlying_id", sa.BigInteger(), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("strike", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("option_type", sa.Enum("CE", "PE", name="option_type"), nullable=True),
        sa.Column(
            "contract_type", sa.Enum("future", "option", name="contract_type"), nullable=False
        ),
        sa.Column("settlement", sa.Enum("cash", "physical", name="settlement"), nullable=False),
        sa.Column("multiplier", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.CheckConstraint(
            "(contract_type = 'future' AND strike IS NULL AND option_type IS NULL) OR "
            "(contract_type = 'option' AND strike IS NOT NULL AND option_type IS NOT NULL)",
            name=op.f("ck_contracts_option_fields_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_contracts_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["underlying_id"],
            ["instruments.id"],
            name=op.f("fk_contracts_underlying_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("instrument_id", name=op.f("pk_contracts")),
    )
    op.create_index(
        "ix_contracts_underlying_expiry", "contracts", ["underlying_id", "expiry"], unique=False
    )
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(
                "split",
                "bonus",
                "dividend",
                "rights",
                "merger",
                "symbol_change",
                "delisting",
                name="corporate_action_type",
            ),
            nullable=False,
        ),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("ratio_from", sa.Integer(), nullable=True),
        sa.Column("ratio_to", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("adjustment_factor", sa.Numeric(precision=18, scale=10), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_corporate_actions_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_corporate_actions")),
    )
    op.create_index(
        "ix_corporate_actions_instrument_ex",
        "corporate_actions",
        ["instrument_id", "ex_date"],
        unique=False,
    )
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exchange_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "rbi_policy",
                "fed",
                "budget",
                "expiry",
                "results",
                "holiday_eve",
                "macro",
                "custom",
                name="event_type",
            ),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=True),
        sa.Column("impact", sa.Enum("low", "medium", "high", name="impact"), nullable=False),
        sa.Column("blocks_trading", sa.Boolean(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name=op.f("fk_events_exchange_id_exchanges"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_events_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index("ix_events_starts_at", "events", ["starts_at"], unique=False)


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("corporate_actions")
    op.drop_table("contracts")
    op.drop_table("instrument_history")
    op.drop_table("instrument_mappings")
    op.drop_table("instruments")
    op.execute("DROP TYPE IF EXISTS instrument_type")
    op.execute("DROP TYPE IF EXISTS history_attribute")
    op.execute("DROP TYPE IF EXISTS option_type")
    op.execute("DROP TYPE IF EXISTS contract_type")
    op.execute("DROP TYPE IF EXISTS settlement")
    op.execute("DROP TYPE IF EXISTS corporate_action_type")
    op.execute("DROP TYPE IF EXISTS event_type")
    op.execute("DROP TYPE IF EXISTS impact")
