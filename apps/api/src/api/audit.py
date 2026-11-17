"""Audit log writes for state-changing endpoints (CLAUDE.md: complete audit trails)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import AuditLog
from core.db.models._enums import ActorType
from core.time import utcnow


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
    db.add(
        AuditLog(
            user_id=user_id,
            actor_type=actor,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            before=before,
            after=after,
            reason=reason,
            ts=utcnow(),
        )
    )
