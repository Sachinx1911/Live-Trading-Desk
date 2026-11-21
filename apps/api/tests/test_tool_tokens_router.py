"""Tool-server token router: owner only; the plaintext token is returned once and never
stored, listed or audited. DB part skipped without TEST_DATABASE_URL_SYNC."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.deps import CurrentUser
from api.routers.tool_tokens import ToolTokenIn, _owner, create, revoke, tokens
from core.db.models import AuditLog, ToolToken, User
from core.services.tool_tokens import hash_token

DB_URL = os.environ.get("TEST_DATABASE_URL_SYNC")
ALEMBIC_INI = Path(__file__).resolve().parents[3] / "infra" / "migrations" / "alembic.ini"


def test_only_the_owner_manages_tokens() -> None:
    _owner(CurrentUser(1, "o@x", ["owner"]))
    with pytest.raises(HTTPException) as exc:
        _owner(CurrentUser(2, "v@x", ["viewer"]))
    assert exc.value.status_code == 403


def test_red_is_not_a_token_level() -> None:
    with pytest.raises(ValueError):
        ToolTokenIn(name="x", max_level="red")  # type: ignore[arg-type]


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    if not DB_URL:
        pytest.skip("TEST_DATABASE_URL_SYNC not set")
    os.environ["ALEMBIC_DATABASE_URL"] = DB_URL
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    engine = create_async_engine(DB_URL.replace("+psycopg", "+asyncpg"))
    async with engine.connect() as conn:
        trans = await conn.begin()
        s = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )()
        try:
            yield s
        finally:
            await s.close()
            await trans.rollback()
    await engine.dispose()


async def test_create_list_revoke_and_audit_without_the_secret(db: AsyncSession) -> None:
    u = User(email=f"tt-{datetime.now(UTC).timestamp()}@example.com", password_hash="x")
    db.add(u)
    await db.flush()
    owner = CurrentUser(u.id, u.email, ["owner"])
    made = await create(ToolTokenIn(name="jarvis mac", max_level="green"), db, owner)
    assert made.token.startswith(made.prefix) and made.max_level == "green"
    listed = await tokens(db, owner)
    assert [t.id for t in listed] == [made.id]
    assert "token" not in listed[0].model_dump()
    row = (await db.execute(select(ToolToken).where(ToolToken.id == made.id))).scalar_one()
    assert row.token_hash == hash_token(made.token)
    out = await revoke(made.id, db, owner)
    assert out.revoked_at is not None
    with pytest.raises(HTTPException) as exc:
        await revoke(made.id + 10_000, db, owner)
    assert exc.value.status_code == 404
    audit = (
        await db.execute(select(AuditLog).where(AuditLog.entity_type == "tool_token"))
    ).scalars()
    blob = "".join(orjson.dumps({"a": a.after, "b": a.before}).decode() for a in audit)
    assert made.token not in blob and row.token_hash not in blob
    assert made.prefix in blob
