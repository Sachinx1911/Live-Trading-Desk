"""Protocol runs (Mark 1 Stage 3.1). The API creates the run row and enqueues; the worker
executes the stored plan step by step (CLAUDE.md: long work never runs inside a request)."""

from __future__ import annotations

from typing import Any

from core.db import get_session_factory
from core.db.models import ProtocolRun
from core.db.models._enums import ActorType
from core.logging import get_logger
from core.notify import build_notifier
from core.secrets import SecretBox
from core.settings import Settings, get_settings
from protocols.context import ActionContext
from protocols.service import execute_run

log = get_logger(__name__)


def secret_box(settings: Settings) -> SecretBox | None:
    try:
        return SecretBox(settings.secrets_key.get_secret_value())
    except ValueError:
        return None


async def run_protocol(ctx: dict[str, Any], run_id: int) -> dict[str, Any]:
    settings = get_settings()
    notifier = build_notifier(settings)
    box = secret_box(settings)
    async with get_session_factory()() as db:

        def make_ctx(run: ProtocolRun) -> ActionContext:
            return ActionContext(
                db=db,
                redis=ctx["redis"],
                settings=settings,
                notifier=notifier,
                user_id=run.user_id,
                actor=ActorType.USER if run.user_id is not None else ActorType.SCHEDULER,
                secret_box=box,
            )

        outcome = await execute_run(db, run_id, make_ctx)
    if outcome is None:
        log.info("protocol.run_skipped", run=run_id)
        return {"run_id": run_id, "status": "skipped"}
    return {"run_id": run_id, "status": outcome.status, "summary": outcome.summary}
