"""Database-backed tests (skipped without TEST_DATABASE_URL_SYNC)."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.calendar import nse_calendar
from core.models import Freshness, Quote, Timeframe
from core.time import IST, utcnow
from market_data.backfill import backfill_candles
from market_data.quality import gap_report
from market_data.repo import quotes as quotes_repo
from market_data.repo.candles import coverage, fetch_candles, latest_ts, upsert_candles
from market_data.repo.instruments import get_by_symbol, get_instrument, provider_token_for, search
from market_data.sync import sync_instrument_master
from providers.fake import FakeMarketDataProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)
cal = nse_calendar()
DAY = date(2026, 11, 17)


def _fake() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(seed=5, tick_interval=0, today=DAY)


async def test_sync_instruments_then_update_is_idempotent(db: AsyncSession) -> None:
    p = _fake()
    r1 = await sync_instrument_master(p, db)
    n = len(await p.fetch_instruments())
    assert r1.new == n and r1.skipped == 0 and len(r1.id_map) == n
    r2 = await sync_instrument_master(p, db)
    assert r2.new == 0 and r2.updated == 0 and r2.unchanged == n
    assert r2.id_map == r1.id_map
    nifty = await get_by_symbol(db, "NSE", "NIFTY")
    assert nifty is not None and nifty.instrument_id == r1.id_map[1]
    fut = await get_instrument(db, r1.id_map[9])
    assert fut is not None and fut.is_derivative and fut.expiry is not None and fut.lot_size == 75
    opt = await get_instrument(db, r1.id_map[10])
    assert opt is not None and opt.strike == Decimal(23950) and opt.option_type is not None
    found = await search(db, "nifty", limit=50)
    assert any(i.symbol == "BANKNIFTY" for i in found)
    assert await provider_token_for(db, nifty.instrument_id, "fake") == "NIFTY"


async def test_candle_upsert_fetch_coverage_latest(db: AsyncSession) -> None:
    p = _fake()
    ids = (await sync_instrument_master(p, db)).id_map
    iid = ids[1]
    s = datetime(2026, 11, 17, tzinfo=IST)
    bars = [
        c.model_copy(update={"instrument_id": iid})
        for c in await p.get_candles(1, Timeframe.M1, s, s + timedelta(days=1))
    ]
    assert await upsert_candles(db, bars) == 375
    assert await upsert_candles(db, bars) == 375  # idempotent
    got = await fetch_candles(db, iid, Timeframe.M1, s, s + timedelta(days=1))
    assert (
        len(got) == 375
        and got[0].ts == bars[0].ts
        and got[0].provider_id == "fake"
        and got[0].is_demo
    )
    assert got[0].close == bars[0].close
    assert await latest_ts(db, iid, Timeframe.M1, "fake") == bars[-1].ts
    cov = await coverage(db, iid)
    assert len(cov) == 1 and cov[0].count == 375 and cov[0].provider_code == "fake"
    # changed value is updated, not duplicated
    changed = bars[0].model_copy(update={"close": bars[0].high})
    await upsert_candles(db, [changed])
    got2 = await fetch_candles(db, iid, Timeframe.M1, s, s + timedelta(days=1))
    assert len(got2) == 375 and got2[0].close == bars[0].high


async def test_backfill_idempotent_and_chunked(db: AsyncSession) -> None:
    p = _fake()
    ids = (await sync_instrument_master(p, db)).id_map
    start = datetime(2026, 11, 2, tzinfo=IST)
    end = datetime(2026, 11, 18, tzinfo=IST)
    p.historical_limits = {Timeframe.M5: 7}  # type: ignore[attr-defined]
    r1 = await backfill_candles(p, db, 1, Timeframe.M5, start, end, db_instrument_id=ids[1])
    r2 = await backfill_candles(p, db, 1, Timeframe.M5, start, end, db_instrument_id=ids[1])
    assert r1.chunks == 3 and r1.rows == r2.rows > 0
    cov = await coverage(db, ids[1])
    assert cov[0].count == 11 * 75  # 11 trading days (2026-11-10 is a holiday)
    assert r1.first_ts == cov[0].first_ts and r1.last_ts == cov[0].last_ts


async def test_gap_report_persists_checks(db: AsyncSession) -> None:
    p = _fake()
    ids = (await sync_instrument_master(p, db)).id_map
    iid = ids[4]
    s = datetime(2026, 11, 17, tzinfo=IST)
    bars = [
        c.model_copy(update={"instrument_id": iid})
        for c in await p.get_candles(4, Timeframe.M1, s, s + timedelta(days=1))
    ]
    await upsert_candles(db, bars[:100] + bars[110:])
    rep = await gap_report(db, iid, DAY, "fake", cal, persist=True)
    assert rep.expected == 375 and rep.present == 365 and rep.missing == 10
    assert (
        len(rep.gaps) == 1
        and rep.gaps[0].minutes == 10
        and rep.coverage_pct == pytest.approx(97.33)
    )
    assert rep.severity.value == "warn"
    from sqlalchemy import func, select

    from core.db.models import DataQualityCheck

    n = (
        await db.execute(
            select(func.count())
            .select_from(DataQualityCheck)
            .where(DataQualityCheck.instrument_id == iid)
        )
    ).scalar_one()
    assert n == 1
    assert (await gap_report(db, iid, date(2026, 11, 15), "fake", cal)).expected == 0


async def test_write_quotes_and_freshness(db: AsyncSession) -> None:
    p = _fake()
    ids = (await sync_instrument_master(p, db)).id_map
    now = utcnow()
    q = Quote(
        instrument_id=ids[1],
        ts=now,
        ltp=Decimal("24000"),
        provider_id="fake",
        received_at=now,
        is_demo=True,
    )
    assert quotes_repo.freshness(q, now) == Freshness.DEMO
    real = q.model_copy(update={"is_demo": False, "provider_id": "upstox"})
    assert quotes_repo.freshness(real, now + timedelta(seconds=1)) == Freshness.LIVE
    assert quotes_repo.freshness(real, now + timedelta(seconds=10)) == Freshness.DELAYED
    assert quotes_repo.freshness(real, now + timedelta(seconds=40)) == Freshness.STALE
    assert await quotes_repo.write_quotes(db, [q, q]) == 2  # duplicate pk ignored, no error


async def test_redis_quote_cache() -> None:
    url = os.environ.get("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set")
    from redis.asyncio import Redis

    r = Redis.from_url(url)
    try:
        await r.ping()
    except Exception:
        pytest.skip("redis not reachable")
    now = datetime.now(UTC)
    q = Quote(
        instrument_id=999_999,
        ts=now,
        ltp=Decimal("1.05"),
        provider_id="fake",
        received_at=now,
        is_demo=True,
    )
    await quotes_repo.cache_quote(r, q, ttl_s=5)
    got = await quotes_repo.get_cached_quote(r, 999_999)
    assert got is not None and got.ltp == Decimal("1.05") and got.freshness == Freshness.DEMO
    many = await quotes_repo.get_cached_quotes(r, [999_999, 999_998])
    assert set(many) == {999_999}
    await r.delete(quotes_repo.cache_key(999_999))
    await r.aclose()
