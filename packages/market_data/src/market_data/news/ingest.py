"""Fetch configured feeds politely and append new headlines (dedup by URL).

Polite behaviour: one GET per feed per run, sequential, a named User-Agent, a timeout, a size
cap and no retries (the next run is 30 minutes later). Failures and frozen feeds are written
to `ingest_errors` so a dead feed is visible instead of silently empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import IngestError, NewsItem
from core.time import utcnow
from market_data.news.feeds import FeedSpec
from market_data.news.parser import FeedParseError, ParsedItem, parse_feed

USER_AGENT = "LiveTradingDesk/0.1 (RSS headline reader; self-hosted trading desk)"
MAX_BYTES = 5 * 1024 * 1024
STALE_AFTER = timedelta(days=7)
ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8"


@dataclass
class FeedResult:
    source: str
    feed_url: str
    fetched: int = 0
    new: int = 0
    newest_published_at: datetime | None = None
    error: str | None = None
    stale: bool = False
    ts: datetime = field(default_factory=utcnow)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "feed_url": self.feed_url,
            "fetched": self.fetched,
            "new": self.new,
            "newest_published_at": (
                self.newest_published_at.isoformat() if self.newest_published_at else None
            ),
            "error": self.error,
            "stale": self.stale,
            "ts": self.ts.isoformat(),
        }


def make_client(timeout_s: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s),
        headers={"User-Agent": USER_AGENT, "Accept": ACCEPT},
        follow_redirects=True,
    )


async def fetch_feed(client: httpx.AsyncClient, url: str) -> bytes:
    async with client.stream("GET", url) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        buf = bytearray()
        async for chunk in resp.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_BYTES:
                raise RuntimeError(f"feed larger than {MAX_BYTES} bytes")
        return bytes(buf)


async def store_items(session: AsyncSession, feed: FeedSpec, items: list[ParsedItem]) -> int:
    """Insert new rows; existing URLs are left untouched (append-only). Returns rows added."""
    if not items:
        return 0
    stmt = (
        insert(NewsItem)
        .values(
            [
                {
                    "source": feed.source,
                    "feed_url": feed.url,
                    "url": it.url,
                    "title": it.title,
                    "summary": it.summary,
                    "published_at": it.published_at,
                }
                for it in items
            ]
        )
        .on_conflict_do_nothing(index_elements=["url"])
        .returning(NewsItem.id)
    )
    return len((await session.execute(stmt)).scalars().all())


async def record_error(session: AsyncSession, feed: FeedSpec, error: str) -> None:
    session.add(IngestError(source=feed.source, feed_url=feed.url, error=error[:1000]))
    await session.flush()


async def ingest_feed(
    session: AsyncSession, client: httpx.AsyncClient, feed: FeedSpec, now: datetime | None = None
) -> FeedResult:
    res = FeedResult(source=feed.source, feed_url=feed.url)
    now = now or utcnow()
    try:
        items = parse_feed(await fetch_feed(client, feed.url))
    except (httpx.HTTPError, RuntimeError, FeedParseError) as exc:
        res.error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        await record_error(session, feed, res.error)
        return res
    res.fetched = len(items)
    dated = [i.published_at for i in items if i.published_at]
    res.newest_published_at = max(dated) if dated else None
    if not items:
        res.error = "feed returned no items"
        await record_error(session, feed, res.error)
        return res
    res.new = await store_items(session, feed, items)
    if res.newest_published_at and now - res.newest_published_at > STALE_AFTER:
        res.stale = True
        res.error = f"stale feed: newest item {res.newest_published_at.date().isoformat()}"
        await record_error(session, feed, res.error)
    return res


async def ingest_feeds(
    session: AsyncSession, feeds: list[FeedSpec], client: httpx.AsyncClient
) -> list[FeedResult]:
    """Each feed is committed on its own so one failure cannot roll back the others."""
    out: list[FeedResult] = []
    for feed in feeds:
        try:
            r = await ingest_feed(session, client, feed)
            await session.commit()
        except Exception as exc:  # DB-level failure for one feed; keep going
            await session.rollback()
            r = FeedResult(source=feed.source, feed_url=feed.url, error=f"store failed: {exc}")
            await record_error(session, feed, r.error or "store failed")
            await session.commit()
        out.append(r)
    return out
