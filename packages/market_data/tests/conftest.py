"""DB fixtures: tests marked with `db` need TEST_DATABASE_URL_SYNC (compose db, trading_test)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from market_data.repo import _lookup

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "infra" / "migrations" / "alembic.ini"
DB_URL = os.environ.get("TEST_DATABASE_URL_SYNC")
needs_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL_SYNC not set")


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    assert DB_URL
    os.environ["ALEMBIC_DATABASE_URL"] = DB_URL
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    yield DB_URL


@pytest.fixture
async def db(migrated_db: str) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after each test."""
    url = migrated_db.replace("+psycopg", "+asyncpg")
    engine = create_async_engine(url)
    _lookup.clear_cache()
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()
    _lookup.clear_cache()
