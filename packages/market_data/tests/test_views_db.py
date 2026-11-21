"""DB-backed accuracy loop: record_view's reference price, the scorer, rebuild and reports
(skipped without TEST_DATABASE_URL_SYNC). Backdated synthetic views live only inside the
test transaction, which is rolled back."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import orjson
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import AiCall, AiObservation, AiViewScore
from core.db.models._enums import AiAgent
from core.models import Candle, Quote, Timeframe
from core.settings import Settings
from core.time import IST
from market_data.repo.candles import upsert_candles
from market_data.repo.instruments import get_by_symbol
from market_data.repo.quotes import cache_key
from market_data.sync import sync_instrument_master
from market_data.views.report import aggregate, ai_spend_by_day, list_views
from market_data.views.scorer import score_views
from market_data.views.service import RecordViewIn, ViewRefused, record_view
from providers.fake import FakeMarketDataProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)

PROVIDER = "dhan"  # a real (non-demo) provider no other test writes candles for
S = Settings(default_market_data_provider=PROVIDER)
T = Decimal("1.0")


class FakeRedis:
    def __init__(self) -> None:
        self.d: dict[str, bytes] = {}

    async def get(self, k: str) -> bytes | None:
        return self.d.get(k)


async def _nifty(db: AsyncSession) -> int:
    await sync_instrument_master(FakeMarketDataProvider(seed=1, tick_interval=0), db)
    ins = await get_by_symbol(db, "NSE", "NIFTY")
    assert ins is not None
    return ins.instrument_id


def _bar(iid: int, tf: Timeframe, ts: datetime, close: str) -> Candle:
    c = Decimal(close)
    return Candle(
        instrument_id=iid,
        timeframe=tf,
        ts=ts,
        open=c,
        high=c,
        low=c,
        close=c,
        provider_id=PROVIDER,
        received_at=ts,
    )


def _daily(iid: int, d: date, close: str) -> Candle:
    return _bar(iid, Timeframe.D1, datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST), close)


def _view(direction: str = "up", h: int = 1, conf: str = "0.8", **kw: Any) -> RecordViewIn:
    return RecordViewIn.model_validate(
        {
            "symbol": "nifty",
            "direction": direction,
            "horizon_days": h,
            "confidence": conf,
            "caller": "jarvis",
            "mode": "jarvis",
            **kw,
        }
    )


async def _count(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(AiObservation))).scalar_one())


async def test_refuses_without_instrument_or_price(db: AsyncSession) -> None:
    await _nifty(db)
    before = await _count(db)
    with pytest.raises(ViewRefused) as e:
        await record_view(db, None, S, _view(symbol="NOPE"), commit=False)
    assert e.value.code == "unknown_instrument"
    with pytest.raises(ViewRefused) as e:
        await record_view(db, FakeRedis(), S, _view(), commit=False)
    assert e.value.code == "no_reference_price"
    assert await _count(db) == before


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        _view(h=0)
    with pytest.raises(ValueError):
        _view(h=251)
    with pytest.raises(ValueError):
        _view(conf="1.2")
    with pytest.raises(ValueError):
        _view(direction="flat")
    with pytest.raises(ValueError):
        _view(invalidation_price="-1")
    with pytest.raises(ValueError):
        _view(ref_price="100")  # the caller never supplies the reference price
    assert _view().symbol == "NIFTY"


async def test_reference_from_last_stored_close_on_a_saturday(db: AsyncSession) -> None:
    iid = await _nifty(db)
    # Thu 19 Nov: last 1m bar 09:33 IST; daily bar of Tue 17 Nov
    await upsert_candles(
        db,
        [
            _bar(iid, Timeframe.M1, datetime(2026, 11, 19, 9, 33, tzinfo=IST), "26010.5"),
            _daily(iid, date(2026, 11, 17), "25900"),
        ],
    )
    sat = datetime(2026, 11, 21, 6, 0, tzinfo=UTC)
    out = await record_view(
        db, FakeRedis(), S, _view(invalidation_price="26500"), now=sat, commit=False
    )
    assert out.ref_price == Decimal("26010.5")
    assert out.ref_source == "dhan:candle_1m" and out.ref_freshness == "historical"
    assert out.ref_ts == datetime(2026, 11, 19, 9, 34, tzinfo=IST)
    assert out.due_date == date(2026, 11, 23)  # Saturday + 1 trading day = Monday
    assert not out.is_demo
    assert any("not below the reference" in w for w in out.warnings)
    assert any("historical" in w for w in out.warnings)
    row = await db.get(AiObservation, out.observation_id)
    assert row is not None and row.ref_source == "dhan:candle_1m"


async def test_daily_bar_used_only_after_its_session_closed(db: AsyncSession) -> None:
    iid = await _nifty(db)
    mon = date(2026, 11, 23)
    await upsert_candles(
        db,
        [
            _bar(iid, Timeframe.M1, datetime(2026, 11, 20, 15, 29, tzinfo=IST), "100"),
            _daily(iid, mon, "200"),
        ],
    )
    during = datetime(2026, 11, 23, 12, 0, tzinfo=IST)
    out = await record_view(db, None, S, _view(), now=during, commit=False)
    assert out.ref_source == "dhan:candle_1m" and out.ref_price == Decimal("100")
    after = datetime(2026, 11, 23, 16, 0, tzinfo=IST)
    out = await record_view(db, None, S, _view(), now=after, commit=False)
    assert out.ref_source == "dhan:candle_1d" and out.ref_price == Decimal("200")


async def test_reference_from_quote_cache_first(db: AsyncSession) -> None:
    iid = await _nifty(db)
    await upsert_candles(db, [_daily(iid, date(2026, 11, 20), "25000")])
    now = datetime(2026, 11, 23, 5, 0, 1, tzinfo=UTC)
    q = Quote(
        instrument_id=iid,
        ts=now - timedelta(seconds=1),
        ltp=Decimal("26111.25"),
        provider_id=PROVIDER,
        received_at=now,
    )
    r = FakeRedis()
    r.d[cache_key(iid)] = orjson.dumps(q.model_dump(mode="json"))
    out = await record_view(db, r, S, _view(), now=now, commit=False)
    assert out.ref_source == "dhan:quote" and out.ref_freshness == "live"
    assert out.ref_price == Decimal("26111.25")
    assert out.warnings == []


async def test_old_cached_quote_loses_to_a_newer_stored_close(db: AsyncSession) -> None:
    """The collector keeps the last quote cached for days: the newer stored close wins."""
    iid = await _nifty(db)
    q = Quote(
        instrument_id=iid,
        ts=datetime(2026, 11, 19, 10, 0, tzinfo=IST),
        ltp=Decimal("25500"),
        provider_id=PROVIDER,
        received_at=datetime(2026, 11, 19, 10, 0, tzinfo=IST),
    )
    r = FakeRedis()
    r.d[cache_key(iid)] = orjson.dumps(q.model_dump(mode="json"))
    await upsert_candles(db, [_daily(iid, date(2026, 11, 20), "25600")])
    sat = datetime(2026, 11, 21, 6, 0, tzinfo=UTC)
    out = await record_view(db, r, S, _view(), now=sat, commit=False)
    assert (out.ref_source, out.ref_price) == ("dhan:candle_1d", Decimal("25600"))
    assert out.ref_ts == datetime(2026, 11, 20, 15, 30, tzinfo=IST)
    # an older close loses to the quote, which is recorded as stale
    r2 = FakeRedis()
    r2.d[cache_key(iid)] = orjson.dumps(
        q.model_copy(update={"ts": datetime(2026, 11, 20, 15, 31, tzinfo=IST)}).model_dump(
            mode="json"
        )
    )
    out = await record_view(db, r2, S, _view(), now=sat, commit=False)
    assert (out.ref_source, out.ref_freshness) == ("dhan:quote", "stale")


async def test_scorer_grades_pending_void_idempotent_and_rebuild(db: AsyncSession) -> None:
    iid = await _nifty(db)
    # reference: Fri 20 Nov daily close 100 (after the close)
    await upsert_candles(db, [_daily(iid, date(2026, 11, 20), "100")])
    fri_eve = datetime(2026, 11, 20, 17, 0, tzinfo=IST)
    ids = {}
    for name, d, h, conf in [
        ("up_hit", "up", 1, "0.9"),  # due Mon 23: close 101.5 -> +1.5 %
        ("down_miss", "down", 1, "0.6"),
        ("side_hit_t2", "sideways", 1, "0.4"),  # +1.5 %: miss at 1 %, hit at 2 %
        ("up_void", "up", 2, "0.75"),  # due Tue 24: never stored -> void after grace
        ("pending", "down", 10, "0.9"),
    ]:
        out = await record_view(db, None, S, _view(d, h, conf), now=fri_eve, commit=False)
        assert out.ref_price == Decimal("100")
        ids[name] = out.observation_id
    await upsert_candles(db, [_daily(iid, date(2026, 11, 23), "101.5")])

    # Mon 15:00 IST: nothing matured yet
    run = await score_views(
        db,
        provider=PROVIDER,
        threshold_pct=T,
        grace_days=3,
        now=datetime(2026, 11, 23, 15, 0, tzinfo=IST),
    )
    assert run.stored == {"hit": 0, "miss": 0, "void": 0} and run.pending == 5

    # Mon 16:30 IST: the three 1-day views are graded
    mon = datetime(2026, 11, 23, 16, 30, tzinfo=IST)
    run = await score_views(db, provider=PROVIDER, threshold_pct=T, grace_days=3, now=mon)
    assert run.stored == {"hit": 1, "miss": 2, "void": 0} and run.pending == 2

    # Tue 24 close missing; grace 3 trading days: Thu 26, Fri 27, Mon 30 (25 is a holiday)
    run = await score_views(
        db,
        provider=PROVIDER,
        threshold_pct=T,
        grace_days=3,
        now=datetime(2026, 11, 27, 16, 30, tzinfo=IST),
    )
    assert run.stored["void"] == 0 and run.pending == 2
    later = datetime(2026, 11, 30, 16, 30, tzinfo=IST)
    run = await score_views(db, provider=PROVIDER, threshold_pct=T, grace_days=3, now=later)
    assert run.stored == {"hit": 0, "miss": 0, "void": 1} and run.pending == 1

    async def snapshot() -> dict[int, tuple[str, Decimal | None, Decimal | None]]:
        rows = (await db.execute(select(AiViewScore))).scalars().all()
        return {r.observation_id: (r.outcome, r.close_price, r.return_pct) for r in rows}

    first = await snapshot()
    assert first[ids["up_hit"]] == ("hit", Decimal("101.5000"), Decimal("1.5000"))
    assert first[ids["down_miss"]][0] == "miss"
    assert first[ids["side_hit_t2"]][0] == "miss"
    assert first[ids["up_void"]] == ("void", None, None)
    assert ids["pending"] not in first

    # idempotent: re-running adds and changes nothing
    run = await score_views(db, provider=PROVIDER, threshold_pct=T, grace_days=3, now=later)
    assert run.stored == {"hit": 0, "miss": 0, "void": 0}
    assert await snapshot() == first

    # rebuild with the same inputs reproduces the same grades
    run = await score_views(
        db, provider=PROVIDER, threshold_pct=T, grace_days=3, now=later, rebuild=True
    )
    assert run.deleted == 4 and sum(run.stored.values()) == 4
    assert await snapshot() == first

    # a late close turns the void into a grade on rebuild; a wider threshold re-grades
    await upsert_candles(db, [_daily(iid, date(2026, 11, 24), "98")])
    await score_views(
        db, provider=PROVIDER, threshold_pct=Decimal("2"), grace_days=3, now=later, rebuild=True
    )
    second = await snapshot()
    assert second[ids["up_void"]][0] == "miss"
    assert second[ids["side_hit_t2"]][0] == "hit"
    assert second[ids["up_hit"]][0] == "miss"  # +1.5 % < 2 %

    # reports
    views = await list_views(db)
    assert {v.status for v in views} == {"hit", "miss", "pending"}
    pend = await list_views(db, status="pending")
    assert [v.id for v in pend] == [ids["pending"]] and pend[0].due_date == date(2026, 12, 7)
    acc = aggregate(views)
    assert acc.overall.total == 5 and acc.overall.pending == 1
    assert acc.overall.hits + acc.overall.misses == 4


async def test_ai_spend_by_day(db: AsyncSession) -> None:
    now = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    for cost in (Decimal("0.010"), None):
        db.add(
            AiCall(
                agent=next(iter(AiAgent)),
                provider="openai",
                model="test",
                prompt_version="v1",
                schema_name="s",
                schema_version="1",
                input_tokens=100,
                output_tokens=50,
                cost_usd=cost,
                latency_ms=10,
                validated=True,
                ts=now - timedelta(hours=1),
            )
        )
    await db.flush()
    days = await ai_spend_by_day(db, days=30, now=now)
    today = [d for d in days if d.day == date(2026, 11, 21)]
    assert today and today[0].calls >= 2 and today[0].calls_without_cost >= 1
    assert today[0].cost_usd is not None and today[0].cost_usd >= Decimal("0.010")
