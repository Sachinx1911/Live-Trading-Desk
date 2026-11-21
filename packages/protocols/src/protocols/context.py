"""What an action may touch: the DB session, Redis, settings, the notifier and who runs it.

Actions never get a broker client or an order gateway: protocols cannot place, modify or
cancel an order (CLAUDE.md rules 1-2). Paper square-offs happen in the paper trader."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models._enums import ActorType
from core.notify import Notifier
from core.secrets import SecretBox
from core.settings import Settings
from core.time import utcnow


@dataclass
class ActionContext:
    db: AsyncSession | None
    redis: Any  # redis.asyncio.Redis; responses may be bytes (arq) or str (API)
    settings: Settings
    notifier: Notifier
    user_id: int | None
    actor: ActorType = ActorType.USER
    secret_box: SecretBox | None = None
    clock: Callable[[], datetime] = field(default=utcnow)

    def now(self) -> datetime:
        return self.clock()

    def session(self) -> AsyncSession:
        if self.db is None:
            raise RuntimeError("this action needs a database session")
        return self.db

    @contextlib.asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        """One step's DB writes: rolled back alone when the step fails, so a failed step
        never poisons the session for the steps after it."""
        if self.db is None:
            yield
            return
        async with self.db.begin_nested():
            yield

    async def redis_text(self, key: str) -> str | None:
        raw = await self.redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)
