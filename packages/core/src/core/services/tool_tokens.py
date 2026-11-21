"""Tool-server service tokens (Mark 1 Stage 4.1, docs/tool-server.md).

One token per tool-server client (e.g. one jarvis install). Only the SHA-256 of a token is
stored; the plaintext is returned once by `create_token` and never again, never logged and
never written to the audit trail. A token carries a `max_level` (green | yellow); the tool
server also has its own ceiling (TOOL_SERVER_MAX_LEVEL) and the lower of the two applies.
Red is never a token level: red actions are not exposed by the tool server at all.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import ToolToken
from core.time import utcnow

# "ltd_" = Live-Trading-Desk: makes a leaked token easy to recognise and scan for.
TOKEN_PREFIX = "ltd_"  # noqa: S105 - a public marker, not a secret
PREFIX_LEN = 12  # characters of the token shown in lists ("ltd_" + 8 random chars)
ToolLevel = Literal["green", "yellow"]
LEVELS: tuple[ToolLevel, ...] = ("green", "yellow")


class ToolTokenError(Exception):
    """A token request that cannot be honoured (bad level, unknown or already revoked)."""


@dataclass(frozen=True)
class NewToken:
    row: ToolToken
    plaintext: str  # shown to the owner once; the caller must not log or store it


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def looks_like_token(value: str) -> bool:
    return value.startswith(TOKEN_PREFIX) and len(value) > len(TOKEN_PREFIX) + 16


async def create_token(
    db: AsyncSession, *, user_id: int, name: str, max_level: str = "green"
) -> NewToken:
    if max_level not in LEVELS:
        raise ToolTokenError(f"max_level must be one of {', '.join(LEVELS)}")
    name = name.strip()
    if not name or len(name) > 80:
        raise ToolTokenError("name must be 1-80 characters")
    plain = generate_token()
    row = ToolToken(
        user_id=user_id,
        name=name,
        token_hash=hash_token(plain),
        prefix=plain[:PREFIX_LEN],
        max_level=max_level,
        created_at=utcnow(),
    )
    db.add(row)
    await db.flush()
    return NewToken(row, plain)


async def list_tokens(db: AsyncSession, user_id: int | None = None) -> list[ToolToken]:
    q = select(ToolToken).order_by(ToolToken.created_at.desc(), ToolToken.id.desc())
    if user_id is not None:
        q = q.where(ToolToken.user_id == user_id)
    return list((await db.execute(q)).scalars())


async def revoke_token(db: AsyncSession, token_id: int, user_id: int | None = None) -> ToolToken:
    row = await db.get(ToolToken, token_id)
    if row is None or (user_id is not None and row.user_id != user_id):
        raise ToolTokenError("token not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        await db.flush()
    return row


@dataclass(frozen=True)
class TokenLookup:
    status: Literal["ok", "missing", "invalid", "revoked"]
    token: ToolToken | None = None


async def lookup_token(db: AsyncSession, presented: str | None) -> TokenLookup:
    """Resolve a presented bearer token. Constant-time compare on the hash; revoked tokens
    are reported as such so the refusal can be logged against the token id."""
    if not presented:
        return TokenLookup("missing")
    digest = hash_token(presented)
    row = (
        await db.execute(select(ToolToken).where(ToolToken.token_hash == digest))
    ).scalar_one_or_none()
    if row is None or not hmac.compare_digest(row.token_hash, digest):
        return TokenLookup("invalid")
    if row.revoked_at is not None:
        return TokenLookup("revoked", row)
    return TokenLookup("ok", row)


async def touch(db: AsyncSession, token_id: int, now: datetime | None = None) -> None:
    await db.execute(
        update(ToolToken).where(ToolToken.id == token_id).values(last_used_at=now or utcnow())
    )
