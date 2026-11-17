"""FastAPI dependencies: app state, db session, current user."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.security import TokenError, decode_access_token
from api.state import AppState
from core.db import get_session_factory

bearer = HTTPBearer(auto_error=False)


def get_state(request: Request) -> AppState:
    return request.app.state.app  # type: ignore[no-any-return]


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


class CurrentUser:
    def __init__(self, user_id: int, email: str, roles: list[str]) -> None:
        self.user_id = user_id
        self.email = email
        self.roles = roles

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles) or "owner" in self.roles


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    state: Annotated[AppState, Depends(get_state)],
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = decode_access_token(creds.credentials, state.settings)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return CurrentUser(int(claims["sub"]), str(claims["email"]), list(claims.get("roles", [])))


def require_roles(*roles: str):  # type: ignore[no-untyped-def]
    async def _check(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not user.has_role(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return _check


State = Annotated[AppState, Depends(get_state)]
DB = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[CurrentUser, Depends(get_current_user)]
