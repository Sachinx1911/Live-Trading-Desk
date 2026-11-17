"""Broker service tests. DB-gated like the core tests."""

import os
from datetime import timedelta

import pytest
from sqlalchemy import select

from core.db.models import BrokerSession, Role, User
from core.secrets import SecretBox
from core.services.brokers import BrokerError, BrokerService
from core.settings import Settings
from core.time import utcnow

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture
async def db():
    # A fresh engine per test: the cached one is bound to another event loop.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(Settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.fixture
def svc(db):
    return BrokerService(db, Settings(), SecretBox(SecretBox.generate_key()))


async def _user(db) -> User:
    role = (await db.execute(select(Role).where(Role.name == "owner"))).scalar_one()
    u = User(email=f"t-{utcnow().timestamp()}@example.com", password_hash="x", is_active=True)
    u.roles.append(role)
    db.add(u)
    await db.flush()
    return u


async def test_account_roundtrip_and_session(db, svc) -> None:
    u = await _user(db)
    st = await svc.status(u.id, "upstox")
    assert st.status == "missing" and not st.configured
    acct = await svc.upsert_account(
        u.id, "upstox", client_code="AB1234", api_key="k", api_secret="s"
    )
    assert svc.credentials(acct) == ("k", "s")
    assert acct.api_key_enc != b"k"
    st = await svc.status(u.id, "upstox")
    assert st.configured and st.status == "missing"
    await svc.store_session(acct, "tok1", utcnow() + timedelta(hours=10))
    assert await svc.valid_token(acct.id) == "tok1"
    s2 = await svc.store_session(acct, "tok2", utcnow() + timedelta(hours=10))
    assert await svc.valid_token(acct.id) == "tok2" and s2.status.value == "valid"
    sessions = (await db.execute(select(BrokerSession))).scalars().all()
    valid = [s for s in sessions if s.broker_account_id == acct.id and s.status.value == "valid"]
    assert len(valid) == 1


async def test_expired_session_marked(db, svc) -> None:
    u = await _user(db)
    acct = await svc.upsert_account(u.id, "upstox", client_code="X", api_key="k", api_secret="s")
    await svc.store_session(acct, "old", utcnow() - timedelta(minutes=1))
    assert await svc.valid_token(acct.id) is None
    assert (await svc.status(u.id, "upstox")).status == "expired"


async def test_unsupported_broker(db, svc) -> None:
    u = await _user(db)
    with pytest.raises(BrokerError):
        await svc.upsert_account(u.id, "zerodha", client_code="Z", api_key=None, api_secret=None)
