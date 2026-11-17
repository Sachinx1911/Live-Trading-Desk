"""Alembic environment. Uses the sync (psycopg) URL from core.settings and the shared
`core.db.Base.metadata`. Importing `core.db.models` registers every table."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import core.db.models  # noqa: F401  (registers tables on Base.metadata)
from core.db.base import Base
from core.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests and CI may point Alembic at a throwaway database.
    return os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_url_sync


def _include_object(obj, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    # Timescale creates internal objects we never model; keep autogenerate quiet about them.
    if type_ == "table" and reflected and compare_to is None:
        return False
    # create_hypertable() adds a default `<table>_ts_idx` index that is not in our metadata.
    if type_ == "index" and reflected and compare_to is None and str(name).endswith("_ts_idx"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
