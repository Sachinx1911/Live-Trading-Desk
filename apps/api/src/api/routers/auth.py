"""Login / refresh / me. Single-operator in v1, multi-user ready (ADR-014)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.deps import DB, State, User
from api.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut
from api.security import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from core.db.models import RefreshSession
from core.db.models import User as UserModel
from core.time import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(u: UserModel) -> UserOut:
    return UserOut(
        id=u.id, email=u.email, display_name=u.display_name, roles=[r.name for r in u.roles]
    )


async def _issue(db: DB, state: State, u: UserModel) -> TokenResponse:
    s = state.settings
    refresh = new_refresh_token()
    db.add(
        RefreshSession(
            user_id=u.id,
            refresh_token_hash=hash_refresh_token(refresh),
            expires_at=utcnow() + timedelta(seconds=s.jwt_refresh_ttl_seconds),
        )
    )
    await db.commit()
    roles = [r.name for r in u.roles]
    return TokenResponse(
        access_token=create_access_token(u.id, u.email, roles, s),
        refresh_token=refresh,
        expires_in=s.jwt_access_ttl_seconds,
        user=_user_out(u),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DB, state: State) -> TokenResponse:
    res = await db.execute(select(UserModel).where(UserModel.email == body.email.lower()))
    u = res.scalar_one_or_none()
    if u is None or not u.is_active or not verify_password(body.password, u.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return await _issue(db, state, u)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DB, state: State) -> TokenResponse:
    res = await db.execute(
        select(RefreshSession).where(
            RefreshSession.refresh_token_hash == hash_refresh_token(body.refresh_token)
        )
    )
    sess = res.scalar_one_or_none()
    now = utcnow()
    if sess is None or sess.revoked_at is not None or sess.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    sess.revoked_at = now  # rotation: a refresh token is single-use
    return await _issue(db, state, sess.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: DB, _: User) -> None:
    res = await db.execute(
        select(RefreshSession).where(
            RefreshSession.refresh_token_hash == hash_refresh_token(body.refresh_token)
        )
    )
    sess = res.scalar_one_or_none()
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = utcnow()
        await db.commit()


@router.get("/me", response_model=UserOut)
async def me(user: User, db: DB) -> UserOut:
    res = await db.execute(select(UserModel).where(UserModel.id == user.user_id))
    u = res.scalar_one_or_none()
    if u is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return _user_out(u)
