"""ORM metadata tests (always run) and real-database migration tests (run when
TEST_DATABASE_URL_SYNC points at a PostgreSQL+TimescaleDB instance, e.g.
`postgresql+psycopg://trading:trading@localhost:5433/trading`)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

import core.db.models  # noqa: F401
from core.db.base import Base

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "infra" / "migrations" / "alembic.ini"

EXPECTED_TABLES = {
    # identity
    "users", "roles", "user_roles", "sessions", "audit_logs", "api_logs",
    # reference
    "exchanges", "markets", "segments", "trading_calendars", "data_providers", "brokers",
    "broker_accounts", "broker_sessions", "cost_schedules",
    # instruments
    "instruments", "instrument_mappings", "instrument_history", "contracts",
    "corporate_actions", "events",
    # strategy
    "strategies", "strategy_versions", "strategy_conditions", "strategy_approvals",
    "strategy_activations",
    # market data
    "historical_candles", "market_quotes", "option_chain_snapshots",
    "data_import_jobs", "data_quality_checks",
    # trading (Phase 3)
    "paper_accounts", "paper_orders", "paper_order_events", "paper_positions", "paper_trades",
    "live_accounts", "live_orders", "live_order_events", "live_positions", "live_trades",
    "reconciliation_runs", "kill_switch_events", "risk_limits",
    "journal_entries", "portfolio_snapshots", "performance_daily",
    # research (Phase 4)
    "backtest_jobs", "backtest_results", "backtest_trades",
    "optimization_jobs", "optimization_results", "replay_sessions",
    # ai (Phase 5)
    "ai_calls",
}  # fmt: skip


def test_metadata_has_all_expected_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_timestamp_column_is_timezone_aware() -> None:
    naive = [
        f"{t.name}.{c.name}"
        for t in Base.metadata.tables.values()
        for c in t.columns
        if isinstance(c.type, sa.DateTime) and not c.type.timezone
    ]
    assert naive == [], f"naive DateTime columns violate ADR-006: {naive}"


def test_hypertable_primary_keys_include_ts() -> None:
    for name in ("historical_candles", "market_quotes", "api_logs"):
        pk_cols = {c.name for c in Base.metadata.tables[name].primary_key.columns}
        assert "ts" in pk_cols, name


# --- real database --------------------------------------------------------------------

DB_URL = os.environ.get("TEST_DATABASE_URL_SYNC")
needs_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL_SYNC not set")


@pytest.fixture(scope="module")
def alembic_cfg() -> Iterator[Config]:
    assert DB_URL
    os.environ["ALEMBIC_DATABASE_URL"] = DB_URL
    cfg = Config(str(ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield cfg
    command.downgrade(cfg, "base")


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    assert DB_URL
    eng = sa.create_engine(DB_URL)
    yield eng
    eng.dispose()


@needs_db
def test_migrations_match_models(alembic_cfg: Config, engine: sa.Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn,
            opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": _include_object,
            },
        )
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], f"schema drift between migrations and models: {diff}"


def _include_object(obj, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    if type_ == "table" and reflected and compare_to is None:
        return False
    if type_ == "index" and reflected and compare_to is None and str(name).endswith("_ts_idx"):
        return False
    return True


@needs_db
def test_hypertables_and_seeds(alembic_cfg: Config, engine: sa.Engine) -> None:
    with engine.connect() as conn:
        hts = set(
            conn.execute(
                sa.text("select hypertable_name from timescaledb_information.hypertables")
            ).scalars()
        )
        assert {"historical_candles", "market_quotes", "api_logs"} <= hts
        assert (
            conn.execute(sa.text("select count(*) from exchanges where code='NSE'")).scalar() == 1
        )
        providers = set(conn.execute(sa.text("select code from data_providers")).scalars())
        assert {"fake", "upstox", "dhan"} <= providers
        roles = set(conn.execute(sa.text("select name from roles")).scalars())
        assert roles == {"owner", "trader", "viewer"}


@needs_db
def test_strategy_version_immutable_after_draft(alembic_cfg: Config, engine: sa.Engine) -> None:
    with engine.begin() as conn:
        uid = conn.execute(
            sa.text(
                "insert into users (email, password_hash, display_name, locale, is_active) "
                "values ('t@example.com', 'x', 't', 'en', true) returning id"
            )
        ).scalar_one()
        sid = conn.execute(
            sa.text(
                "insert into strategies (user_id, name, category, origin, tags, is_archived) "
                "values (:u, 's', 'trend', 'user_nl', '{}', false) returning id"
            ),
            {"u": uid},
        ).scalar_one()
        vid = conn.execute(
            sa.text(
                "insert into strategy_versions (strategy_id, version_no, status, dsl, "
                "dsl_schema_version, dsl_hash, created_by) values "
                "(:s, 1, 'draft', '{\"a\": 1}'::jsonb, '1.0', 'h1', 'user') returning id"
            ),
            {"s": sid},
        ).scalar_one()
        # draft: editable
        conn.execute(
            sa.text("update strategy_versions set dsl = '{\"a\": 2}'::jsonb where id = :v"),
            {"v": vid},
        )
        # leaving draft sets frozen_at
        conn.execute(
            sa.text("update strategy_versions set status = 'backtested' where id = :v"), {"v": vid}
        )
        frozen = conn.execute(
            sa.text("select frozen_at from strategy_versions where id = :v"), {"v": vid}
        ).scalar_one()
        assert frozen is not None
        # status transitions still allowed
        conn.execute(
            sa.text("update strategy_versions set status = 'validated' where id = :v"), {"v": vid}
        )
    with engine.connect() as conn, pytest.raises(sa.exc.DBAPIError) as excinfo:
        conn.execute(
            sa.text("update strategy_versions set dsl = '{\"a\": 3}'::jsonb where id = :v"),
            {"v": vid},
        )
    assert "immutable" in str(excinfo.value)
    with engine.begin() as conn:
        conn.execute(sa.text("delete from users where id = :u"), {"u": uid})


@needs_db
def test_trading_partial_unique_indexes_and_fks(alembic_cfg: Config, engine: sa.Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "select indexname, indexdef from pg_indexes where indexname in "
                "('uq_paper_positions_open', 'uq_live_positions_open', 'uq_risk_limits_active')"
            )
        ).all()
        defs = {name: d for name, d in rows}
        assert set(defs) == {
            "uq_paper_positions_open",
            "uq_live_positions_open",
            "uq_risk_limits_active",
        }
        for d in defs.values():
            assert "UNIQUE" in d and "WHERE" in d, d
        fks = set(
            conn.execute(
                sa.text(
                    "select conname from pg_constraint where contype='f' "
                    "and conrelid='strategy_activations'::regclass"
                )
            ).scalars()
        )
        assert {
            "fk_strategy_activations_paper_account_id_paper_accounts",
            "fk_strategy_activations_live_account_id_live_accounts",
        } <= fks
        # paper and live never share a table (ADR-008)
        cols = set(
            conn.execute(
                sa.text(
                    "select column_name from information_schema.columns "
                    "where table_name='paper_orders'"
                )
            ).scalars()
        )
        assert "live_account_id" not in cols and "broker_order_id" not in cols


@needs_db
def test_downgrade_leaves_no_custom_types(alembic_cfg: Config, engine: sa.Engine) -> None:
    command.downgrade(alembic_cfg, "base")
    try:
        with engine.connect() as conn:
            tables = set(
                conn.execute(
                    sa.text(
                        "select table_name from information_schema.tables "
                        "where table_schema='public'"
                    )
                ).scalars()
            )
            enums = set(
                conn.execute(
                    sa.text(
                        "select t.typname from pg_type t "
                        "join pg_namespace n on n.oid=t.typnamespace "
                        "where n.nspname='public' and t.typtype='e'"
                    )
                ).scalars()
            )
        assert tables <= {"alembic_version"}, tables
        assert enums == set(), enums
    finally:
        command.upgrade(alembic_cfg, "head")
