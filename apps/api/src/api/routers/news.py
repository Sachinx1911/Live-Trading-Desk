"""Raw news headlines (Mark 1 Stage 3.5). Read-only here; fetching runs in the worker.

Symbol tags are computed at query time by a deterministic matcher over our instruments
(no AI, nothing stored). `symbol=` filters on those tags."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.audit import audit
from api.deps import DB, State, User
from market_data.news.feeds import parse_feed_list
from market_data.news.repo import item_dict, list_news, matcher_for, source_stats

router = APIRouter(prefix="/news", tags=["news"])

SYMBOL_SCAN_CAP = 3000  # newest rows scanned when filtering by symbol


class NewsItemOut(BaseModel):
    id: int
    source: str
    url: str
    title: str
    summary: str | None
    published_at: datetime | None
    fetched_at: datetime
    symbols: list[str]


class NewsListOut(BaseModel):
    items: list[NewsItemOut]
    count: int
    symbol: str | None
    scanned: int


class NewsSourceOut(BaseModel):
    source: str
    feed_url: str
    configured: bool
    items: int
    newest_published_at: datetime | None
    last_new_item_at: datetime | None
    last_fetch_at: datetime | None
    last_fetch_new: int | None
    last_fetch_items: int | None
    last_fetch_error: str | None
    stale: bool
    last_error_at: datetime | None
    last_error: str | None


class NewsSourcesOut(BaseModel):
    sources: list[NewsSourceOut]
    last_run_at: datetime | None


@router.get("", response_model=NewsListOut)
async def news(
    db: DB,
    state: State,
    _: User,
    since: datetime | None = None,
    source: str | None = None,
    q: str | None = Query(None, max_length=100),
    symbol: str | None = Query(None, max_length=40),
    limit: int = Query(100, ge=1, le=500),
) -> NewsListOut:
    provider = state.settings.default_market_data_provider
    matcher = await matcher_for(db, provider)
    sym = symbol.strip().upper() if symbol else None
    rows = await list_news(
        db, since=since, source=source, q=q, limit=SYMBOL_SCAN_CAP if sym else limit
    )
    out: list[NewsItemOut] = []
    for r in rows:
        tags = matcher.tags(r.title, r.summary)
        if sym and sym not in tags:
            continue
        out.append(NewsItemOut.model_validate(item_dict(r, tags)))
        if len(out) >= limit:
            break
    return NewsListOut(items=out, count=len(out), symbol=sym, scanned=len(rows))


@router.get("/sources", response_model=NewsSourcesOut)
async def sources(db: DB, state: State, _: User) -> NewsSourcesOut:
    configured = parse_feed_list(state.settings.news_feeds)
    stats = await source_stats(db)
    try:
        raw: dict[str, str] = await state.redis.hgetall("news:feeds")  # type: ignore[misc]
        last_run = await state.redis.get("news:last_run")
    except Exception:  # Redis down: DB stats still answer
        raw, last_run = {}, None
    runs: dict[str, dict[str, Any]] = {k: orjson.loads(v) for k, v in raw.items()}
    urls = [f.url for f in configured] + [u for u in stats if u not in {f.url for f in configured}]
    names = {f.url: f.source for f in configured}
    out: list[NewsSourceOut] = []
    for url in urls:
        st = stats.get(url)
        run = runs.get(url) or {}
        out.append(
            NewsSourceOut(
                source=names.get(url) or (st.source if st else url),
                feed_url=url,
                configured=url in names,
                items=st.items if st else 0,
                newest_published_at=st.newest_published_at if st else None,
                last_new_item_at=st.last_new_item_at if st else None,
                last_fetch_at=run.get("ts"),
                last_fetch_new=run.get("new"),
                last_fetch_items=run.get("fetched"),
                last_fetch_error=run.get("error"),
                stale=bool(run.get("stale")),
                last_error_at=st.last_error_at if st else None,
                last_error=st.last_error if st else None,
            )
        )
    return NewsSourcesOut(sources=out, last_run_at=last_run)


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest(db: DB, state: State, user: User) -> dict[str, str]:
    """Queue one ingest run in the worker (owner only). Nothing is fetched in this request."""
    if not user.has_role("owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner only")
    pool = await create_pool(RedisSettings.from_dsn(state.settings.redis_url))
    try:
        await pool.enqueue_job("ingest_news", True)
    finally:
        await pool.aclose()
    await audit(db, user_id=user.user_id, action="news.ingest.enqueue", entity_type="news")
    await db.commit()
    return {"status": "queued"}
