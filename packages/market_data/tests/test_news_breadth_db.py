"""DB-backed news ingest (dedup, errors, stale feeds) and breadth storage
(skipped without TEST_DATABASE_URL_SYNC). Network is mocked with httpx.MockTransport."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import IngestError, MarketBreadth, NewsItem
from core.models import Timeframe
from core.time import IST
from market_data.breadth.repo import latest_breadth, list_breadth, load_closes
from market_data.breadth.service import compute_and_store
from market_data.news.feeds import FeedSpec
from market_data.news.ingest import USER_AGENT, ingest_feeds
from market_data.news.repo import list_news, source_stats, tracked_entries
from market_data.news.tagger import SymbolMatcher
from market_data.repo.candles import upsert_candles
from market_data.sync import sync_instrument_master
from providers.fake import FakeMarketDataProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)
RSS = (Path(__file__).parent / "fixtures" / "news" / "rss_sample.xml").read_bytes()
GOOD = FeedSpec("https://good.example.com/rss", "Good")
DOWN = FeedSpec("https://down.example.com/rss", "Down")
HTML = FeedSpec("https://html.example.com/rss", "Html")


def _client(seen: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "good.example.com":
            return httpx.Response(200, content=RSS)
        if req.url.host == "html.example.com":
            return httpx.Response(200, content=b"<html>blocked</html>")
        return httpx.Response(503)

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )


async def test_ingest_dedups_by_url_and_records_errors(db: AsyncSession) -> None:
    seen: list[httpx.Request] = []
    async with _client(seen) as client:
        r1 = await ingest_feeds(db, [GOOD, DOWN, HTML], client)
        r2 = await ingest_feeds(db, [GOOD], client)
    good, down, html = r1
    assert (good.fetched, good.new) == (3, 3)
    assert good.error is None or good.stale  # the fixture ages; a stale feed is still stored
    assert down.error == "RuntimeError: HTTP 503" and down.new == 0
    assert html.error is not None and html.error.startswith("FeedParseError")
    assert r2[0].new == 0 and r2[0].fetched == 3  # same URLs: nothing appended
    assert len(seen) == 4  # one GET per feed per run, no retries
    assert all(r.headers["User-Agent"] == USER_AGENT for r in seen)
    n = (await db.execute(select(func.count()).select_from(NewsItem))).scalar_one()
    assert n == 3
    feeds = {
        e.feed_url
        for e in (await db.execute(select(IngestError))).scalars()
        if e.feed_url != GOOD.url
    }  # GOOD may carry a "stale feed" row once the fixture is older than 7 days
    assert feeds == {DOWN.url, HTML.url}
    stats = await source_stats(db)
    assert stats[GOOD.url].items == 3 and stats[DOWN.url].items == 0
    assert stats[DOWN.url].last_error == "RuntimeError: HTTP 503"
    rows = await list_news(db, q="reliance", limit=10)
    assert [r.title[:8] for r in rows] == ["Reliance"]
    # undated items sort by fetch time, so the undated one (fetched now) comes first
    newest_first = await list_news(db, limit=10)
    assert [r.published_at for r in newest_first] == [
        None,
        datetime(2026, 11, 20, 10, 15, tzinfo=UTC),
        datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    ]


async def _seed_fake_daily(db: AsyncSession, days: int = 320) -> dict[int, int]:
    p = FakeMarketDataProvider(seed=11, tick_interval=0, today=date(2026, 11, 17))
    ids = (await sync_instrument_master(p, db)).id_map
    end = datetime(2026, 11, 18, tzinfo=IST)
    start = end - timedelta(days=days)
    for fake_id in (1, 2, 3, 4, 5, 6, 7, 8):  # indices + 5 NIFTY 50 stocks
        bars = await p.get_candles(fake_id, Timeframe.D1, start, end)
        await upsert_candles(
            db, [b.model_copy(update={"instrument_id": ids[fake_id]}) for b in bars]
        )
    return ids


async def test_breadth_compute_store_and_read(db: AsyncSession) -> None:
    await _seed_fake_daily(db)
    closes = await load_closes(
        db,
        provider="fake",
        symbols=["RELIANCE", "TCS", "HDFCBANK", "INFY", "SBIN"],
        start=date(2026, 1, 1),
        end=date(2026, 11, 17),
    )
    assert set(closes["symbol"].unique().to_list()) == {
        "RELIANCE",
        "TCS",
        "HDFCBANK",
        "INFY",
        "SBIN",
    }
    last_day = max(closes["day"].to_list())
    run = await compute_and_store(
        db, provider="fake", universe="NIFTY50", start=last_day - timedelta(days=10), end=last_day
    )
    assert run.rows and run.rows[-1].as_of_date == last_day
    latest = run.rows[-1]
    assert latest.universe_size == 5
    assert latest.advances + latest.declines + latest.unchanged == 5
    assert "NIFTY" in latest.index_moves and "INDIAVIX" in latest.index_moves
    assert len(latest.missing) == 45
    # idempotent: second run updates, no duplicates
    await compute_and_store(
        db, provider="fake", universe="NIFTY50", start=last_day - timedelta(days=10), end=last_day
    )
    n = (await db.execute(select(func.count()).select_from(MarketBreadth))).scalar_one()
    assert n == len(run.rows)
    row = await latest_breadth(db, provider="fake", universe="NIFTY50")
    assert row is not None and row.as_of_date == last_day and row.advances == latest.advances
    hist = await list_breadth(db, provider="fake", universe="NIFTY50")
    assert [h.as_of_date for h in hist] == [r.as_of_date for r in run.rows]
    # another provider sees nothing (never mixed)
    assert await latest_breadth(db, provider="upstox", universe="NIFTY50") is None


async def test_tracked_entries_feed_the_matcher(db: AsyncSession) -> None:
    await _seed_fake_daily(db, days=20)
    entries = await tracked_entries(db, "fake")
    syms = {e.symbol for e in entries}
    assert {"NIFTY", "RELIANCE", "SBIN"} <= syms
    m = SymbolMatcher(entries)
    assert m.tags("Reliance Industries and State Bank of India rally") == ["RELIANCE", "SBIN"]
