"""Append-only `ai_calls` writer. Each record commits in its own session so a failed job
transaction can never erase the evidence that a call was made (ADR-009)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm.calls import AiCallEntry
from core.db import get_session_factory
from core.db.models import AiCall
from core.db.models._enums import AiAgent


class DbAiCallLogger:
    def __init__(self, session_factory: Callable[[], AsyncSession] | None = None) -> None:
        self._factory = session_factory

    def _session(self) -> AsyncSession:
        factory = self._factory or get_session_factory()
        return factory()

    async def record(self, entry: AiCallEntry) -> int | None:
        row = AiCall(
            agent=AiAgent(entry.agent),
            provider=entry.provider,
            model=entry.model,
            prompt_version=entry.prompt_version,
            schema_name=entry.schema_name,
            schema_version=entry.schema_version,
            input_refs=entry.input_refs,
            input_tokens=entry.input_tokens,
            output_tokens=entry.output_tokens,
            cost_usd=entry.cost_usd,
            latency_ms=entry.latency_ms,
            validated=entry.validated,
            error=entry.error,
            job_id=entry.job_id,
            user_id=entry.user_id,
            payload_uri=entry.payload_uri,
        )
        async with self._session() as db:
            db.add(row)
            await db.commit()
            return row.id
