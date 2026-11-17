from __future__ import annotations

from typing import Any

from core.logging import get_logger
from core.time import utcnow

log = get_logger(__name__)


async def heartbeat(ctx: dict[str, Any]) -> str:
    """Proves the worker loop and Redis connection are alive. Written to Redis for /health."""
    ts = utcnow().isoformat()
    await ctx["redis"].set("worker:heartbeat", ts, ex=600)
    log.info("worker.heartbeat", at=ts)
    return ts
