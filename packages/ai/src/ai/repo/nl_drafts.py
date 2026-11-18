"""DraftRepo over `strategy_nl_drafts`. The record is stored as its JSON parts so the
clarification thread and every ai_call id survive exactly as the service saw them."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.nl_builder.extraction import ClarificationQuestion
from ai.nl_builder.service import (
    DraftRecord,
    GenerateRequest,
    ThreadMessage,
    ValidationView,
)
from core.db.models import StrategyNlDraft
from core.db.models._enums import NlDraftStatus


class DbDraftRepo:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _to_row(rec: DraftRecord, row: StrategyNlDraft | None = None) -> StrategyNlDraft:
        row = row or StrategyNlDraft(draft_id=rec.draft_id, user_id=rec.user_id)
        row.status = NlDraftStatus(rec.status)
        row.request = rec.request.model_dump(mode="json")
        row.extraction = rec.extraction
        row.dsl = rec.dsl
        row.validation = rec.validation.model_dump(mode="json")
        row.missing_information = list(rec.missing_information)
        row.questions = [q.model_dump(mode="json") for q in rec.questions]
        row.defaults_applied = list(rec.defaults_applied)
        row.unsupported = list(rec.unsupported)
        row.changes = list(rec.changes)
        row.thread = [m.model_dump(mode="json") for m in rec.thread]
        row.ai_call_ids = list(rec.ai_call_ids)
        row.strategy_version_id = rec.strategy_version_id
        return row

    @staticmethod
    def _to_record(row: StrategyNlDraft) -> DraftRecord:
        return DraftRecord(
            draft_id=row.draft_id,
            user_id=row.user_id,
            status=row.status.value,
            request=GenerateRequest.model_validate(row.request),
            extraction=row.extraction,
            dsl=row.dsl,
            validation=ValidationView.model_validate(row.validation),
            missing_information=list(row.missing_information),
            questions=[ClarificationQuestion.model_validate(q) for q in row.questions],
            defaults_applied=list(row.defaults_applied),
            unsupported=list(row.unsupported),
            changes=list(row.changes),
            thread=[ThreadMessage.model_validate(m) for m in row.thread],
            ai_call_ids=[int(i) for i in row.ai_call_ids],
            strategy_version_id=row.strategy_version_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def create(self, rec: DraftRecord) -> None:
        self.db.add(self._to_row(rec))
        await self.db.flush()

    async def _row(self, draft_id: str, user_id: int) -> StrategyNlDraft | None:
        res = await self.db.execute(
            select(StrategyNlDraft).where(
                StrategyNlDraft.draft_id == draft_id, StrategyNlDraft.user_id == user_id
            )
        )
        return res.scalar_one_or_none()

    async def get(self, draft_id: str, user_id: int) -> DraftRecord | None:
        row = await self._row(draft_id, user_id)
        return self._to_record(row) if row is not None else None

    async def save(self, rec: DraftRecord) -> None:
        row = await self._row(rec.draft_id, rec.user_id)
        if row is None:
            raise LookupError(f"draft {rec.draft_id} not found")
        self._to_row(rec, row)
        await self.db.flush()
