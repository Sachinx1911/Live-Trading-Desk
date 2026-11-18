"""regime: regime_daily, regime_intraday; regime tags on backtest results/trades (Module 6)

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = {
    "regime_trend": ("up", "down", "sideways"),
    "regime_strength": ("weak", "moderate", "strong"),
    "regime_volatility": ("low", "normal", "high"),
    "regime_structure": ("bullish", "bearish", "range"),
    "regime_day_type": ("trending", "range", "volatile_open", "unknown"),
}


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)
    enum = {n: postgresql.ENUM(*v, name=n, create_type=False) for n, v in ENUMS.items()}
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "regime_daily",
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("trend", enum["regime_trend"], nullable=False),
        sa.Column("strength", enum["regime_strength"], nullable=False),
        sa.Column("volatility", enum["regime_volatility"], nullable=False),
        sa.Column("structure", enum["regime_structure"], nullable=False),
        sa.Column("adx", sa.Numeric(8, 2), nullable=True),
        sa.Column("ema20", sa.Numeric(14, 4), nullable=True),
        sa.Column("ema50", sa.Numeric(14, 4), nullable=True),
        sa.Column("ema200", sa.Numeric(14, 4), nullable=True),
        sa.Column("atr_pct", sa.Numeric(8, 3), nullable=True),
        sa.Column("vix", sa.Numeric(8, 2), nullable=True),
        sa.Column("vix_percentile", sa.Numeric(5, 1), nullable=True),
        sa.Column("event_day", sa.Boolean(), nullable=False),
        sa.Column("events", jsonb, nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_regime_daily_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "date", name=op.f("pk_regime_daily")),
    )
    op.create_index("ix_regime_daily_date", "regime_daily", ["date"])

    op.create_table(
        "regime_intraday",
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day_type", enum["regime_day_type"], nullable=False),
        sa.Column("or_high", sa.Numeric(14, 4), nullable=True),
        sa.Column("or_low", sa.Numeric(14, 4), nullable=True),
        sa.Column("vwap_distance_pct", sa.Numeric(8, 3), nullable=True),
        sa.Column("atr_ratio", sa.Numeric(8, 3), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_regime_intraday_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instrument_id", "ts", name=op.f("pk_regime_intraday")),
    )

    op.add_column("backtest_results", sa.Column("regime_table", jsonb, nullable=True))
    op.add_column("backtest_trades", sa.Column("regime", jsonb, nullable=True))


def downgrade() -> None:
    op.drop_column("backtest_trades", "regime")
    op.drop_column("backtest_results", "regime_table")
    op.drop_table("regime_intraday")
    op.drop_index("ix_regime_daily_date", table_name="regime_daily")
    op.drop_table("regime_daily")
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
