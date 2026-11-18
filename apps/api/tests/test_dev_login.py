"""Development-only auto-login: exists only when DEV_AUTO_LOGIN_EMAIL is set outside
production, issues real tokens for that user, and can never be configured in production."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routers.auth import dev_login
from api.security import decode_access_token
from core.settings import Settings


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, jwt_secret="unit-test-secret-0123456789abcdef", **kw)  # type: ignore[call-arg]


class _Result:
    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class _FakeDB:
    """Just enough of AsyncSession for the route: one SELECT, one add, one commit."""

    def __init__(self, user: Any) -> None:
        self.user = user
        self.added: list[Any] = []
        self.committed = False

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(self.user)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


def _owner() -> Any:
    return SimpleNamespace(
        id=7,
        email="owner@example.com",
        display_name="",
        is_active=True,
        roles=[SimpleNamespace(name="owner")],
    )


def test_settings_refuse_dev_auto_login_in_production() -> None:
    with pytest.raises(ValidationError, match="APP_ENV=production"):
        _settings(app_env="production", dev_auto_login_email="owner@example.com")
    assert not _settings(app_env="production").dev_auto_login_enabled
    assert not _settings(app_env="development").dev_auto_login_enabled
    assert _settings(app_env="development", dev_auto_login_email="x@y.z").dev_auto_login_enabled


async def test_dev_login_is_404_when_disabled() -> None:
    state = SimpleNamespace(settings=_settings(app_env="development"))
    db = _FakeDB(_owner())
    with pytest.raises(HTTPException) as exc:
        await dev_login(db, state)  # type: ignore[arg-type]
    assert exc.value.status_code == 404
    assert db.added == [] and not db.committed


async def test_dev_login_issues_tokens_for_configured_user() -> None:
    settings = _settings(app_env="development", dev_auto_login_email="Owner@Example.com")
    state = SimpleNamespace(settings=settings)
    db = _FakeDB(_owner())
    tok = await dev_login(db, state)  # type: ignore[arg-type]
    claims = decode_access_token(tok.access_token, settings)
    assert claims["sub"] == "7" and claims["roles"] == ["owner"]
    assert tok.user.email == "owner@example.com"
    assert len(db.added) == 1 and db.committed  # refresh session persisted like a real login


async def test_dev_login_rejects_missing_or_inactive_user() -> None:
    settings = _settings(app_env="development", dev_auto_login_email="owner@example.com")
    state = SimpleNamespace(settings=settings)
    with pytest.raises(HTTPException) as exc:
        await dev_login(_FakeDB(None), state)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    inactive = _owner()
    inactive.is_active = False
    with pytest.raises(HTTPException) as exc:
        await dev_login(_FakeDB(inactive), state)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
