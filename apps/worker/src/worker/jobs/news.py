"""Raw news ingest job (Mark 1 Stage 3.5): every 30 minutes 07:00-22:30 IST. No AI.

Each feed's outcome is kept in Redis hash `news:feeds` (feed URL -> JSON) for
`GET /news/sources`; failures also go to the `ingest_errors` table."""

from __future__ import annotations

from datetime import time
from typing import Any

import orjson

from core.db import get_session_factory
from core.logging import get_logger
from core.settings import get_settings
from core.time import IST, utcnow
from market_data.news.feeds import parse_feed_list
from market_data.news.ingest import ingest_feeds, make_client

log = get_logger(__name__)

WINDOW_START = time(7, 0)
WINDOW_END = time(22, 30)
REDIS_FEEDS_KEY = "news:feeds"
REDIS_LAST_RUN_KEY = "news:last_run"


def in_window(now_ist: time) -> bool:
    return WINDOW_START <= now_ist <= WINDOW_END


async def ingest_news(ctx: dict[str, Any], force: bool = False) -> dict[str, Any]:
    """`force=True` (owner button / API) ignores the 07:00-22:30 IST window."""
    now = utcnow()
    if not force and not in_window(now.astimezone(IST).time()):
        return {"skipped": "outside 07:00-22:30 IST"}
    s = get_settings()
    feeds = parse_feed_list(s.news_feeds)
    async with make_client(s.news_fetch_timeout_s) as client, get_session_factory()() as db:
        results = await ingest_feeds(db, feeds, client)
    out = {r.source: r.as_dict() for r in results}
    redis = ctx.get("redis")
    if redis is not None:
        mapping = {r.feed_url: orjson.dumps(r.as_dict()).decode() for r in results}
        if mapping:
            await redis.hset(REDIS_FEEDS_KEY, mapping=mapping)
        await redis.set(REDIS_LAST_RUN_KEY, now.isoformat(), ex=7 * 24 * 3600)
    log.info(
        "news.ingest",
        **{r.source: f"fetched={r.fetched} new={r.new} err={r.error}" for r in results},
    )
    return {
        "ts": now.isoformat(),
        "feeds": out,
        "new": sum(r.new for r in results),
        "fetched": sum(r.fetched for r in results),
    }
