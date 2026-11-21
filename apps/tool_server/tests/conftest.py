"""Tool-server DB fixtures: tests marked `needs_db` need TEST_DATABASE_URL_SYNC (compose db,
trading_test). Each test runs inside a transaction that is rolled back; the service's own
sessions join it through savepoints."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from market_data.repo import _lookup

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "infra" / "migrations" / "alembic.ini"
DB_URL = os.environ.get("TEST_DATABASE_URL_SYNC")


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    assert DB_URL
    os.environ["ALEMBIC_DATABASE_URL"] = DB_URL
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    yield DB_URL


@pytest.fixture
async def conn(migrated_db: str) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(migrated_db.replace("+psycopg", "+asyncpg"))
    _lookup.clear_cache()
    async with engine.connect() as c:
        trans = await c.begin()
        try:
            yield c
        finally:
            await trans.rollback()
    await engine.dispose()
    _lookup.clear_cache()


@pytest.fixture
def session_factory(conn: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s
