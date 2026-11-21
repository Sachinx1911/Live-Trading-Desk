"""JARVIS accuracy loop (Mark 1 Stage 4.6): grade matured views after the close, and rebuild.

`score_ai_views` runs daily at 16:30 IST (after the daily candle refresh at 15:45 IST) and on
any day it is enqueued; it grades observations whose due date has closed, from the stored daily
candles of the active provider (DEFAULT_MARKET_DATA_PROVIDER) with VIEW_SCORE_THRESHOLD_PCT.
A view whose due-date close is still missing VIEW_SCORE_GRACE_DAYS trading days later is void.
`rebuild_ai_view_scores` deletes every score and grades everything again (same rules), e.g.
after a threshold change or a late candle back-fill. No LLM runs here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from core.db import get_session_factory
from core.logging import get_logger
from core.settings import get_settings
from core.time import utcnow
from market_data.views.scorer import score_views

log = get_logger(__name__)


async def _run(rebuild: bool) -> dict[str, Any]:
    s = get_settings()
    provider = s.default_market_data_provider
    threshold = Decimal(str(s.view_score_threshold_pct))
    async with get_session_factory()() as db:
        run = await score_views(
            db,
            provider=provider,
            threshold_pct=threshold,
            grace_days=s.view_score_grace_days,
            now=utcnow(),
            rebuild=rebuild,
        )
        await db.commit()
    out = run.summary() | {"provider": provider, "threshold_pct": str(threshold)}
    log.info("ai_views.scored", **out)
    return out


async def score_ai_views(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(rebuild=False)


async def rebuild_ai_view_scores(ctx: dict[str, Any]) -> dict[str, Any]:
    return await _run(rebuild=True)
