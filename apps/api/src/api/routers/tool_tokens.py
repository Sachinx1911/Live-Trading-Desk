"""Tool-server tokens and the tool-call log (Mark 1 Stage 4.1, docs/tool-server.md). Owner only.

The plaintext token is returned once, by POST /tool-tokens, and never again: only its SHA-256
is stored, and neither the token nor its hash goes into the audit trail or the logs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.audit import audit
from api.deps import DB, CurrentUser, User
from core.db.models import ToolCall, ToolToken
from core.services.tool_tokens import ToolTokenError, create_token, list_tokens, revoke_token

router = APIRouter(tags=["tool-server"])


def _owner(user: CurrentUser) -> None:
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the owner manages tool-server tokens")


class ToolTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    max_level: Literal["green", "yellow"] = "green"


class ToolTokenOut(BaseModel):
    id: int
    name: str
    prefix: str
    max_level: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ToolTokenCreated(ToolTokenOut):
    token: str = Field(description="shown once; store it in the client's keychain")


class ToolCallOut(BaseModel):
    id: int
    ts: datetime
    token_id: int | None
    token_name: str | None
    transport: str
    tool: str
    level: str | None
    args: dict[str, Any]
    status: str
    error: str | None
    duration_ms: int | None
    result_meta: dict[str, Any]


def _out(t: ToolToken) -> ToolTokenOut:
    return ToolTokenOut(
        id=t.id,
        name=t.name,
        prefix=t.prefix,
        max_level=t.max_level,
        created_at=t.created_at,
        last_used_at=t.last_used_at,
        revoked_at=t.revoked_at,
    )


@router.post("/tool-tokens", response_model=ToolTokenCreated, status_code=status.HTTP_201_CREATED)
async def create(body: ToolTokenIn, db: DB, user: User) -> ToolTokenCreated:
    _owner(user)
    try:
        new = await create_token(db, user_id=user.user_id, name=body.name, max_level=body.max_level)
    except ToolTokenError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="tool_token.create",
        entity_type="tool_token",
        entity_id=new.row.id,
        after={"name": new.row.name, "prefix": new.row.prefix, "max_level": new.row.max_level},
    )
    await db.commit()
    return ToolTokenCreated(**_out(new.row).model_dump(), token=new.plaintext)


@router.get("/tool-tokens", response_model=list[ToolTokenOut])
async def tokens(db: DB, user: User) -> list[ToolTokenOut]:
    _owner(user)
    return [_out(t) for t in await list_tokens(db, user.user_id)]


@router.post("/tool-tokens/{token_id}/revoke", response_model=ToolTokenOut)
async def revoke(token_id: int, db: DB, user: User) -> ToolTokenOut:
    _owner(user)
    try:
        row = await revoke_token(db, token_id, user.user_id)
    except ToolTokenError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await audit(
        db,
        user_id=user.user_id,
        action="tool_token.revoke",
        entity_type="tool_token",
        entity_id=row.id,
        after={"name": row.name, "prefix": row.prefix, "revoked_at": row.revoked_at.isoformat()}
        if row.revoked_at
        else None,
    )
    await db.commit()
    return _out(row)


@router.get("/tool-calls", response_model=list[ToolCallOut])
async def tool_calls(
    db: DB,
    user: User,
    tool: Annotated[str | None, Query(max_length=64)] = None,
    status_filter: Annotated[
        Literal["ok", "error", "refused"] | None, Query(alias="status")
    ] = None,
    token_id: int | None = None,
    transport: Literal["http", "mcp"] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ToolCallOut]:
    _owner(user)
    q = (
        select(ToolCall, ToolToken.name)
        .outerjoin(ToolToken, ToolToken.id == ToolCall.token_id)
        .order_by(ToolCall.ts.desc(), ToolCall.id.desc())
        .limit(limit)
    )
    if tool:
        q = q.where(ToolCall.tool == tool)
    if status_filter:
        q = q.where(ToolCall.status == status_filter)
    if token_id is not None:
        q = q.where(ToolCall.token_id == token_id)
    if transport:
        q = q.where(ToolCall.transport == transport)
    return [
        ToolCallOut(
            id=c.id,
            ts=c.ts,
            token_id=c.token_id,
            token_name=name,
            transport=c.transport,
            tool=c.tool,
            level=c.level,
            args=c.args or {},
            status=c.status,
            error=c.error,
            duration_ms=c.duration_ms,
            result_meta=c.result_meta or {},
        )
        for c, name in (await db.execute(q)).all()
    ]
