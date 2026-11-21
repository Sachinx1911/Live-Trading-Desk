"""Audit log writes for state-changing endpoints (CLAUDE.md: complete audit trails)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models._enums import ActorType
from core.services.audit import write_audit


async def audit(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    actor: ActorType = ActorType.USER,
) -> None:
    write_audit(
        db,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
        actor=actor,
    )
