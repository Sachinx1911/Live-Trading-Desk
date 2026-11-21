"""Shared helpers for the tool server tests (imported by conftest and the tests).

No-DB tests use `FakeService` (in-memory tokens and call log). DB tests (marked by
`needs_db`) need TEST_DATABASE_URL_SYNC (compose db, trading_test); each test runs inside a
transaction that is rolled back, and the service's sessions join it through savepoints.
"""

from __future__ import annotations

import os
from typing import Any

import fakeredis.aioredis
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from core.settings import Settings
from tool_server.service import Caller, Outcome, ToolService

DB_URL = os.environ.get("TEST_DATABASE_URL_SYNC")
needs_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL_SYNC not set")

# Fake secrets seeded so the secret-scan tests can prove they never leave the server.
FAKE_SECRETS_KEY = Fernet.generate_key().decode()
FAKE_JWT_SECRET = "jwt-secret-for-tests-0123456789abcdef"


def make_settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {
        "secrets_key": SecretStr(FAKE_SECRETS_KEY),
        "jwt_secret": SecretStr(FAKE_JWT_SECRET),
        "default_market_data_provider": "fake",
        "tool_server_max_level": "green",
        "tool_server_rate_per_minute": 600,
    }
    base.update(kw)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


# ----------------------------------------------------------------------------- no DB
class FakeDb:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def __aenter__(self) -> FakeDb:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeService(ToolService):
    """ToolService with tokens and the call log in memory (the call path is the real one)."""

    tokens: dict[str, Caller]
    logged: list[dict[str, Any]]

    async def authenticate(self, presented: str | None) -> Caller:
        if not presented:
            return Caller("missing")
        return self.tokens.get(presented, Caller("invalid"))

    async def _log(self, **kw: Any) -> Outcome:  # type: ignore[override]
        outcome: Outcome = kw["outcome"]
        presented = kw["presented"]
        if outcome.message:
            outcome.message = self._scrub_text(outcome.message, presented)
        self.logged.append(
            {
                "tool": kw["tool"],
                "transport": kw["transport"],
                "status": outcome.status,
                "code": outcome.code,
                "args": kw["args"],
                "token_id": kw["caller"].token_id,
                "error": outcome.message,
            }
        )
        outcome.call_id = len(self.logged)
        outcome.tool = self._scrub_text(kw["tool"], presented)[:64] or "?"
        return outcome


def fake_service(catalogue: Any, server_level: str = "green", **kw: Any) -> FakeService:
    svc = FakeService(
        settings=make_settings(tool_server_max_level=server_level, **kw),
        session_factory=FakeDb,  # type: ignore[arg-type]
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        catalogue=catalogue,
    )
    svc.tokens = {}
    svc.logged = []
    return svc
