"""Natural-language strategy builder (API spec §8.1).

POST /strategies/generate                  description -> draft + questions
GET  /strategies/generate/{draft_id}       current draft
POST /strategies/generate/{draft_id}/answer answers -> updated draft (changes listed)
POST /strategies/generate/{draft_id}/save   draft DSL -> new strategy + DRAFT version

The LLM only ever produces the draft record; saving is a user act and goes through the
same version-creation path as the editor (validation included).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm import BudgetExceededError, LLMNotConfiguredError, LLMOutputError, LLMTransportError
from ai.nl_builder import (
    AnswerRequest,
    DraftRecord,
    DraftResponse,
    GenerateRequest,
    NLStrategyBuilder,
    UnknownQuestionError,
    draft_response,
)
from ai.repo import DbDraftRepo
from api.audit import audit
from api.deps import DB, State, User
from api.routers import strategies as strategies_router
from api.state import AppState
from core.db.models import Exchange, Instrument, StrategyVersion
from core.db.models._enums import StrategyCategory, StrategyOrigin

router = APIRouter(prefix="/strategies/generate", tags=["strategies"])


class SaveIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: StrategyCategory = StrategyCategory.OTHER
    tags: list[str] = []


def _error(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _builder(state: AppState, db: AsyncSession) -> NLStrategyBuilder:
    async def resolve(market: str, symbol: str) -> list[str]:
        res = await db.execute(
            select(Instrument.id)
            .join(Exchange, Exchange.id == Instrument.exchange_id)
            .where(Instrument.symbol == symbol.strip().upper(), Exchange.code == market.upper())
            .order_by(Instrument.id)
            .limit(5)
        )
        return [str(i) for i in res.scalars().all()]

    return NLStrategyBuilder(
        state.llm, state.ai_logger, daily=state.ai_daily, instrument_resolver=resolve
    )


async def _run(coro: Any) -> Any:
    try:
        return await coro
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            _error("ai_not_configured", "AI is not configured on this server (OPENAI_API_KEY)."),
        ) from exc
    except BudgetExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, _error("ai_budget_exceeded", str(exc))
        ) from exc
    except LLMOutputError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            _error(
                "ai_invalid_output",
                f"The model's draft did not match the expected structure ({exc}). "
                "Try rephrasing the description.",
            ),
        ) from exc
    except LLMTransportError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, _error("ai_upstream_error", str(exc))
        ) from exc


async def _draft(repo: DbDraftRepo, draft_id: str, user: User) -> DraftRecord:
    rec = await repo.get(draft_id, user.user_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return rec


@router.post("", response_model=DraftResponse, status_code=status.HTTP_201_CREATED)
async def generate(body: GenerateRequest, db: DB, state: State, user: User) -> DraftResponse:
    rec: DraftRecord = await _run(_builder(state, db).generate(body, user_id=user.user_id))
    repo = DbDraftRepo(db)
    await repo.create(rec)
    await audit(
        db,
        user_id=user.user_id,
        action="strategy.nl.generate",
        entity_type="strategy_nl_draft",
        entity_id=rec.draft_id,
        after={"ai_call_ids": rec.ai_call_ids, "missing": rec.missing_information},
    )
    await db.commit()
    return draft_response(rec)


@router.get("/{draft_id}", response_model=DraftResponse)
async def get_draft(draft_id: str, db: DB, user: User) -> DraftResponse:
    return draft_response(await _draft(DbDraftRepo(db), draft_id, user))


@router.post("/{draft_id}/answer", response_model=DraftResponse)
async def answer(
    draft_id: str, body: AnswerRequest, db: DB, state: State, user: User
) -> DraftResponse:
    repo = DbDraftRepo(db)
    rec = await _draft(repo, draft_id, user)
    try:
        rec = await _run(_builder(state, db).answer(rec, body))
    except UnknownQuestionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await repo.save(rec)
    await audit(
        db,
        user_id=user.user_id,
        action="strategy.nl.answer",
        entity_type="strategy_nl_draft",
        entity_id=rec.draft_id,
        after={"ai_call_ids": rec.ai_call_ids, "changes": rec.changes[:20]},
    )
    await db.commit()
    return draft_response(rec)


@router.post(
    "/{draft_id}/save",
    response_model=strategies_router.VersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def save(draft_id: str, body: SaveIn, db: DB, user: User) -> strategies_router.VersionOut:
    """Create the strategy container and its first DRAFT version from the draft's DSL.
    Validation errors (422) come from the same path the editor uses."""
    repo = DbDraftRepo(db)
    rec = await _draft(repo, draft_id, user)
    if rec.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"draft already {rec.status}")
    name = body.name or str(rec.dsl.get("name") or rec.request.instrument)
    strategy = await strategies_router.create_strategy(
        strategies_router.StrategyIn(
            name=name[:120],
            category=body.category,
            origin=StrategyOrigin.USER_NL,
            description=rec.request.description[:500],
            tags=body.tags,
        ),
        db,
        user,
    )
    version = await strategies_router.create_version(
        strategy.id,
        strategies_router.VersionIn(
            dsl=rec.dsl,
            source_text=rec.request.description,
            source_language=str(rec.dsl.get("language") or rec.request.language or "en"),
            change_summary="Created from the natural-language builder",
        ),
        db,
        user,
    )
    row = (
        await db.execute(select(StrategyVersion).where(StrategyVersion.id == version.id))
    ).scalar_one()
    row.ai_call_id = rec.ai_call_ids[-1] if rec.ai_call_ids else None
    rec.status = "saved"
    rec.strategy_version_id = version.id
    await repo.save(rec)
    await audit(
        db,
        user_id=user.user_id,
        action="strategy.nl.save",
        entity_type="strategy_version",
        entity_id=version.id,
        after={"draft_id": rec.draft_id, "ai_call_id": row.ai_call_id},
    )
    await db.commit()
    return version
