"""Password hashing (Argon2) and JWT access/refresh tokens (ADR-014)."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.settings import Settings
from core.time import utcnow

_hasher = PasswordHasher()
ALGO = "HS256"


class TokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: int, email: str, roles: list[str], settings: Settings) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "roles": roles,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGO)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[ALGO]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc
    if claims.get("type") != "access":
        raise TokenError("not an access token")
    return claims


def new_refresh_token() -> str:
    """Opaque random token; only its hash is stored (refresh_sessions table)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()
