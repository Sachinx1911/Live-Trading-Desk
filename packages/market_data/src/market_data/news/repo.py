"""Read side of the raw news store and the instrument list the symbol matcher uses."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import Exchange, HistoricalCandle, IngestError, NewsItem
from core.db.models import Instrument as InstrumentRow
from core.db.models._enums import InstrumentType
from core.models import Timeframe
from market_data.news.tagger import SymbolEntry, SymbolMatcher
from market_data.repo._lookup import provider_id

_MATCHER_TTL_S = 600.0
_matcher_cache: dict[str, tuple[float, SymbolMatcher]] = {}


@dataclass(frozen=True)
class SourceStats:
    source: str
    feed_url: str
    items: int
    newest_published_at: datetime | None
    last_new_item_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None


async def list_news(
    session: AsyncSession,
    *,
    since: datetime | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[NewsItem]:
    """Newest first by published time (fetch time when the feed gave none)."""
    order = func.coalesce(NewsItem.published_at, NewsItem.fetched_at)
    stmt = select(NewsItem)
    if since is not None:
        stmt = stmt.where(order >= since)
    if source:
        stmt = stmt.where(NewsItem.source == source)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(NewsItem.title.ilike(like) | NewsItem.summary.ilike(like))
    stmt = stmt.order_by(order.desc(), NewsItem.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def source_stats(session: AsyncSession) -> dict[str, SourceStats]:
    """Keyed by feed URL: stored item counts plus the latest ingest error."""
    rows = (
        await session.execute(
            select(
                NewsItem.feed_url,
                func.max(NewsItem.source),
                func.count(),
                func.max(NewsItem.published_at),
                func.max(NewsItem.fetched_at),
            ).group_by(NewsItem.feed_url)
        )
    ).all()
    out: dict[str, SourceStats] = {
        url: SourceStats(src, url, n, newest, fetched, None, None)
        for url, src, n, newest, fetched in rows
    }
    last_err = (
        select(IngestError.feed_url, func.max(IngestError.id).label("mid"))
        .group_by(IngestError.feed_url)
        .subquery()
    )
    errs = (
        await session.execute(select(IngestError).join(last_err, IngestError.id == last_err.c.mid))
    ).scalars()
    for e in errs:
        base = out.get(e.feed_url) or SourceStats(e.source, e.feed_url, 0, None, None, None, None)
        out[e.feed_url] = SourceStats(
            base.source,
            base.feed_url,
            base.items,
            base.newest_published_at,
            base.last_new_item_at,
            e.ts,
            e.error,
        )
    return out


async def recent_errors(session: AsyncSession, limit: int = 20) -> list[IngestError]:
    q = select(IngestError).order_by(IngestError.ts.desc()).limit(limit)
    return list((await session.execute(q)).scalars())


async def tracked_entries(session: AsyncSession, provider: str) -> list[SymbolEntry]:
    """NSE equities and indices that have daily candles from `provider` ("our instruments")."""
    pid = await provider_id(session, provider)
    has_daily = exists().where(
        HistoricalCandle.instrument_id == InstrumentRow.id,
        HistoricalCandle.timeframe == Timeframe.D1,
        HistoricalCandle.provider_id == pid,
    )
    q = (
        select(InstrumentRow.symbol, InstrumentRow.name)
        .join(Exchange, Exchange.id == InstrumentRow.exchange_id)
        .where(
            Exchange.code == "NSE",
            InstrumentRow.instrument_type.in_((InstrumentType.EQUITY, InstrumentType.INDEX)),
            has_daily,
        )
    )
    return [SymbolEntry(symbol=s, name=n) for s, n in (await session.execute(q)).all()]


async def matcher_for(session: AsyncSession, provider: str) -> SymbolMatcher:
    """Cached for 10 minutes per provider; the instrument set changes rarely."""
    hit = _matcher_cache.get(provider)
    now = time.monotonic()
    if hit and now - hit[0] < _MATCHER_TTL_S:
        return hit[1]
    m = SymbolMatcher(await tracked_entries(session, provider))
    _matcher_cache[provider] = (now, m)
    return m


def clear_matcher_cache() -> None:
    _matcher_cache.clear()


def item_dict(row: NewsItem, symbols: list[str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "source": row.source,
        "url": row.url,
        "title": row.title,
        "summary": row.summary,
        "published_at": row.published_at,
        "fetched_at": row.fetched_at,
        "symbols": symbols,
    }
