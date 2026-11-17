"""reference data (exchanges, providers, brokers, costs) with seeds

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exchanges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("session_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exchanges")),
        sa.UniqueConstraint("code", name=op.f("uq_exchanges_code")),
    )
    op.create_table(
        "markets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exchange_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name=op.f("fk_markets_exchange_id_exchanges"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_markets")),
        sa.UniqueConstraint("exchange_id", "code", name=op.f("uq_markets_exchange_id")),
    )
    op.create_table(
        "segments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("settlement", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
            name=op.f("fk_segments_market_id_markets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_segments")),
        sa.UniqueConstraint("market_id", "code", name=op.f("uq_segments_market_id")),
    )
    op.create_table(
        "trading_calendars",
        sa.Column("exchange_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "session_type",
            sa.Enum("normal", "holiday", "special", "muhurat", "half_day", name="session_type"),
            nullable=False,
        ),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name=op.f("fk_trading_calendars_exchange_id_exchanges"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("exchange_id", "date", name=op.f("pk_trading_calendars")),
    )
    op.create_table(
        "data_providers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_providers")),
        sa.UniqueConstraint("code", name=op.f("uq_data_providers_code")),
    )
    op.create_table(
        "brokers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("supports_data", sa.Boolean(), nullable=False),
        sa.Column("supports_trading", sa.Boolean(), nullable=False),
        sa.Column("auth_type", sa.Enum("oauth2", "token", name="auth_type"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brokers")),
        sa.UniqueConstraint("code", name=op.f("uq_brokers_code")),
    )
    op.create_table(
        "broker_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("broker_id", sa.BigInteger(), nullable=False),
        sa.Column("client_code", sa.Text(), nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("api_secret_enc", sa.LargeBinary(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
            ["broker_id"],
            ["brokers.id"],
            name=op.f("fk_broker_accounts_broker_id_brokers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_broker_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_accounts")),
        sa.UniqueConstraint(
            "user_id", "broker_id", "client_code", name=op.f("uq_broker_accounts_user_id")
        ),
    )
    op.create_index(
        op.f("ix_broker_accounts_user_id"), "broker_accounts", ["user_id"], unique=False
    )
    op.create_table(
        "broker_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("broker_account_id", sa.BigInteger(), nullable=False),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("valid", "expired", "revoked", name="broker_session_status"),
            nullable=False,
        ),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_broker_sessions_broker_account_id_broker_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_sessions")),
    )
    op.create_index(
        op.f("ix_broker_sessions_broker_account_id"),
        "broker_sessions",
        ["broker_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broker_sessions_expires_at"), "broker_sessions", ["expires_at"], unique=False
    )
    op.create_table(
        "cost_schedules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exchange_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "product",
            sa.Enum("intraday", "delivery", "futures", "options", name="cost_product"),
            nullable=False,
        ),
        sa.Column(
            "charge_type",
            sa.Enum(
                "brokerage",
                "stt",
                "exchange_txn",
                "sebi",
                "stamp_duty",
                "gst",
                "clearing",
                name="charge_type",
            ),
            nullable=False,
        ),
        sa.Column("side", sa.Enum("buy", "sell", "both", name="charge_side"), nullable=False),
        sa.Column(
            "rate_type",
            sa.Enum("percent", "flat_per_order", "per_lot", name="rate_type"),
            nullable=False,
        ),
        sa.Column("rate", sa.Numeric(precision=12, scale=8), nullable=False),
        sa.Column("cap", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_cost_schedules_effective_range"),
        ),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["exchanges.id"],
            name=op.f("fk_cost_schedules_exchange_id_exchanges"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.id"],
            name=op.f("fk_cost_schedules_segment_id_segments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_schedules")),
    )
    op.create_index(
        "ix_cost_schedules_lookup",
        "cost_schedules",
        ["exchange_id", "segment_id", "product", "charge_type", "effective_from"],
        unique=False,
    )

    # --- reference seeds (never user or market data) ---------------------------------
    op.execute(
        """
        INSERT INTO exchanges (code, name, timezone, currency, country, session_rules) VALUES (
            'NSE', 'National Stock Exchange of India', 'Asia/Kolkata', 'INR', 'IN',
            '{"regular": {"open": "09:15", "close": "15:30", "square_off": "15:20",
              "no_new_entries_after": "14:45"},
              "pre_open": {"open": "09:00", "close": "09:08"},
              "weekly_holidays": [5, 6]}'::jsonb
        )
        """
    )
    op.execute(
        """
        INSERT INTO markets (exchange_id, code, name)
        SELECT id, m.code, m.name FROM exchanges,
          (VALUES ('EQ', 'Equity'), ('FO', 'Futures & Options'), ('CD', 'Currency Derivatives'))
          AS m(code, name)
        WHERE exchanges.code = 'NSE'
        """
    )
    op.execute(
        """
        INSERT INTO segments (market_id, code, settlement)
        SELECT mk.id, s.code, s.settlement FROM markets mk
        JOIN exchanges e ON e.id = mk.exchange_id AND e.code = 'NSE'
        JOIN (VALUES ('EQ', 'CASH', 'T+1'), ('EQ', 'INDEX', 'none'),
                     ('FO', 'FUT', 'cash'), ('FO', 'OPT', 'cash'),
                     ('CD', 'FUT', 'cash'), ('CD', 'OPT', 'cash'))
          AS s(market_code, code, settlement) ON s.market_code = mk.code
        """
    )
    op.execute(
        """
        INSERT INTO data_providers (code, name, capabilities, is_demo, is_active) VALUES
          ('fake',   'Fake (demo) provider', '{"depth_levels": 5, "tick": true}'::jsonb,
           true, true),
          ('upstox', 'Upstox', '{"depth_levels": 30, "tick": true, "historical": true}'::jsonb,
           false, true),
          ('dhan',   'Dhan', '{"depth_levels": 20, "tick": true, "historical": true}'::jsonb,
           false, false),
          ('import', 'File import', '{}'::jsonb, false, true)
        """
    )
    op.execute(
        """
        INSERT INTO brokers (code, name, supports_data, supports_trading, auth_type) VALUES
          ('upstox', 'Upstox', true, true, 'oauth2'),
          ('dhan',   'Dhan',   true, true, 'token')
        """
    )
    op.execute(
        """
        INSERT INTO roles (name, permissions) VALUES
          ('owner',  '["*"]'::jsonb),
          ('trader', '["strategies:*", "backtests:*", "paper:*", "live:*", "portfolio:read",
                       "market:read", "ai:*"]'::jsonb),
          ('viewer', '["strategies:read", "backtests:read", "paper:read", "live:read",
                       "portfolio:read", "market:read"]'::jsonb)
        """
    )


def downgrade() -> None:
    op.drop_table("cost_schedules")
    op.drop_table("broker_sessions")
    op.drop_table("broker_accounts")
    op.drop_table("brokers")
    op.drop_table("data_providers")
    op.drop_table("trading_calendars")
    op.drop_table("segments")
    op.drop_table("markets")
    op.drop_table("exchanges")
    op.execute("DROP TYPE IF EXISTS session_type")
    op.execute("DROP TYPE IF EXISTS auth_type")
    op.execute("DROP TYPE IF EXISTS broker_session_status")
    op.execute("DROP TYPE IF EXISTS cost_product")
    op.execute("DROP TYPE IF EXISTS charge_type")
    op.execute("DROP TYPE IF EXISTS charge_side")
    op.execute("DROP TYPE IF EXISTS rate_type")
