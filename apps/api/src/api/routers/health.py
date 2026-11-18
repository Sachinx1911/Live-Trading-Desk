from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from ai.llm import llm_status
from api.deps import State
from core.db import get_session_factory

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str  # ok | degraded
    version: str
    env: str
    db: str  # ok | error
    redis: str
    provider: str
    secrets_configured: bool
    llm: str  # not_configured | <provider>:<model>


@router.get("/health", response_model=HealthResponse)
async def health(state: State) -> HealthResponse:
    from api.main import VERSION

    db = "ok"
    try:
        async with get_session_factory()() as s:
            await s.execute(text("select 1"))
    except Exception:
        db = "error"
    redis = "ok"
    try:
        await state.redis.ping()
    except Exception:
        redis = "error"
    ph = await state.provider.health()
    status = "ok" if db == "ok" and redis == "ok" else "degraded"
    return HealthResponse(
        status=status,
        version=VERSION,
        env=state.settings.app_env,
        db=db,
        redis=redis,
        provider=f"{ph.code}:{ph.state.value}",
        secrets_configured=state.settings.secrets_configured,
        llm=llm_status(state.settings),
    )
