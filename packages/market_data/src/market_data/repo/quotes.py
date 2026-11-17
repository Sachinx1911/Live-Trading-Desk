"""market_quotes rows and the Redis latest-quote cache, plus the freshness rule."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import orjson
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import MarketQuote
from core.db.models._enums import QuoteFreshness
from core.models import Freshness, Quote
from core.time import ensure_utc, utcnow
from market_data.repo._lookup import provider_id

LIVE_WITHIN = timedelta(seconds=2)
DELAYED_WITHIN = timedelta(seconds=30)
CACHE_TTL_S = 60


def freshness(quote: Quote, now: datetime | None = None) -> Freshness:
    """Freshness per ADR thresholds: live < 2 s, delayed < 30 s, else stale; demo wins."""
    if quote.is_demo:
        return Freshness.DEMO
    age = ensure_utc(now or utcnow()) - ensure_utc(quote.ts)
    if age < LIVE_WITHIN:
        return Freshness.LIVE
    if age < DELAYED_WITHIN:
        return Freshness.DELAYED
    return Freshness.STALE


def _db_freshness(f: Freshness) -> QuoteFreshness:
    if f in (Freshness.LIVE, Freshness.DEMO):
        return QuoteFreshness.LIVE
    if f == Freshness.DELAYED:
        return QuoteFreshness.DELAYED
    return QuoteFreshness.STALE


async def write_quotes(
    session: AsyncSession, quotes: Sequence[Quote], now: datetime | None = None
) -> int:
    if not quotes:
        return 0
    rows = []
    for q in quotes:
        rows.append(
            {
                "instrument_id": q.instrument_id,
                "ts": q.ts,
                "provider_id": await provider_id(session, q.provider_id),
                "ltp": q.ltp,
                "bid_px": q.bid,
                "ask_px": q.ask,
                "bid_qty": q.bid_qty,
                "ask_qty": q.ask_qty,
                "volume": q.volume,
                "oi": q.oi,
                "provider_ts": q.provider_ts,
                "freshness": _db_freshness(freshness(q, now)),
            }
        )
    stmt = (
        insert(MarketQuote)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["instrument_id", "ts", "provider_id"])
    )
    await session.execute(stmt)
    return len(rows)


_DT_FIELDS = ("ts", "provider_ts", "received_at")


def _from_json(data: dict[str, Any]) -> Quote:
    """Cached payloads carry ISO strings; the canonical validators expect datetimes."""
    for f in _DT_FIELDS:
        v = data.get(f)
        if isinstance(v, str):
            data[f] = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return Quote.model_validate(data)


def cache_key(instrument_id: int) -> str:
    return f"quote:{instrument_id}"


async def cache_quote(redis: Redis, quote: Quote, ttl_s: int = CACHE_TTL_S) -> None:
    payload = quote.model_dump(mode="json")
    await redis.set(cache_key(quote.instrument_id), orjson.dumps(payload), ex=ttl_s)


async def get_cached_quote(
    redis: Redis, instrument_id: int, now: datetime | None = None
) -> Quote | None:
    raw = await redis.get(cache_key(instrument_id))
    if raw is None:
        return None
    q = _from_json(orjson.loads(raw))
    return q.model_copy(update={"freshness": freshness(q, now)})


async def get_cached_quotes(
    redis: Redis, instrument_ids: Sequence[int], now: datetime | None = None
) -> dict[int, Quote]:
    if not instrument_ids:
        return {}
    raws = await redis.mget([cache_key(i) for i in instrument_ids])
    out: dict[int, Quote] = {}
    for iid, raw in zip(instrument_ids, raws, strict=True):
        if raw is not None:
            q = _from_json(orjson.loads(raw))
            out[iid] = q.model_copy(update={"freshness": freshness(q, now)})
    return out
