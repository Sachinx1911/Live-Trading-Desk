"""EDITH hook for JARVIS views (Mark 1 Stage 4.6): an alert when price crosses a recorded
view's invalidation price. Pure rule tests plus one DB test of the fact gathering."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import fakeredis.aioredis
import orjson
import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import AiObservation, AiViewScore
from core.models import Quote
from market_data.repo.instruments import get_by_symbol
from market_data.repo.quotes import cache_key
from market_data.sync import sync_instrument_master
from protocols.alert_store import store_alerts, view_facts
from protocols.alerts import AlertFacts, AlertParams, ViewFact, evaluate, view_invalidated
from providers.fake import FakeMarketDataProvider

NOW = datetime(2026, 11, 23, 5, 0, tzinfo=UTC)  # Monday 10:30 IST
P = AlertParams()


def _view(price: str | None, inv: str = "23800", ref: str = "24000", **kw: object) -> ViewFact:
    base: dict[str, object] = {
        "observation_id": 7,
        "symbol": "NIFTY",
        "instrument_id": 1,
        "direction": "up",
        "ref_price": Decimal(ref),
        "invalidation_price": Decimal(inv),
        "invalidation": "view wrong below 23,800",
        "price": Decimal(price) if price is not None else None,
        "price_ts": NOW - timedelta(seconds=5) if price is not None else None,
    }
    base.update(kw)
    return ViewFact(**base)  # type: ignore[arg-type]


def _facts(*views: ViewFact) -> AlertFacts:
    return AlertFacts(now=NOW, market_open=True, views=views)


def test_below_level_crossed_once() -> None:
    assert view_invalidated(_facts(_view("23850")), P) == []
    out = view_invalidated(_facts(_view("23800")), P)  # touching the level counts
    assert [(a.kind, a.dedup_key, a.severity) for a in out] == [
        ("view_invalidated", "view_invalidated:7", "info")
    ]
    assert out[0].data["side"] == "below" and out[0].instrument_id == 1
    assert "view wrong below 23,800" in out[0].message
    assert view_invalidated(_facts(_view("23700", already_alerted=True)), P) == []


def test_above_level_for_a_down_view() -> None:
    v = _view("24210", inv="24200", direction="down")
    out = view_invalidated(_facts(v), P)
    assert len(out) == 1 and out[0].data["side"] == "above"
    assert view_invalidated(_facts(_view("24150", inv="24200", direction="down")), P) == []


def test_missing_stale_or_equal_not_judged() -> None:
    assert view_invalidated(_facts(_view(None)), P) == []
    stale = _view("23000", price_ts=NOW - timedelta(minutes=10))
    assert view_invalidated(_facts(stale), P) == []
    assert view_invalidated(_facts(_view("23000", inv="24000")), P) == []  # level == ref


def test_evaluate_includes_view_rule() -> None:
    assert "view_invalidated" in {a.kind for a in evaluate(_facts(_view("23000")), P)}


@given(
    ref=st.decimals(min_value=100, max_value=50000, places=2),
    inv=st.decimals(min_value=100, max_value=50000, places=2),
    price=st.decimals(min_value=100, max_value=50000, places=2),
)
def test_fires_iff_price_on_far_side_of_level(ref: Decimal, inv: Decimal, price: Decimal) -> None:
    out = view_invalidated(_facts(_view(str(price), inv=str(inv), ref=str(ref))), P)
    if inv == ref:
        assert out == []
    elif inv < ref:
        assert bool(out) == (price <= inv)
    else:
        assert bool(out) == (price >= inv)


# ---------------------------------------------------------------- DB: fact gathering
@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL_SYNC"), reason="TEST_DATABASE_URL_SYNC not set"
)
async def test_view_facts_open_views_real_quotes_and_once(db: AsyncSession) -> None:
    await sync_instrument_master(FakeMarketDataProvider(seed=1, tick_interval=0), db)
    ins = await get_by_symbol(db, "NSE", "NIFTY")
    assert ins is not None
    now = datetime.now(UTC)

    def obs(inv: str | None) -> AiObservation:
        return AiObservation(
            ts=now - timedelta(days=1),
            caller="test",
            instrument_id=ins.instrument_id,
            direction="up",
            horizon_days=5,
            confidence=Decimal("0.7"),
            invalidation_price=Decimal(inv) if inv else None,
            ref_price=Decimal("24000"),
            ref_source="dhan:candle_1d",
            ref_freshness="historical",
            ref_ts=now - timedelta(days=1),
        )

    open_v, no_level, scored = obs("23800"), obs(None), obs("23900")
    db.add_all([open_v, no_level, scored])
    await db.flush()
    db.add(
        AiViewScore(
            observation_id=scored.id,
            due_date=now.date(),
            threshold_pct=Decimal(1),
            outcome="miss",
        )
    )
    await db.flush()
    redis = fakeredis.aioredis.FakeRedis()

    def quote(demo: bool) -> bytes:
        q = Quote(
            instrument_id=ins.instrument_id,
            ts=now,
            ltp=Decimal("23750"),
            provider_id="fake" if demo else "dhan",
            received_at=now,
            is_demo=demo,
        )
        return orjson.dumps(q.model_dump(mode="json"))

    await redis.set(cache_key(ins.instrument_id), quote(demo=True))
    facts = await view_facts(db, redis, now)
    mine = [f for f in facts if f.observation_id in {open_v.id, no_level.id, scored.id}]
    assert [f.observation_id for f in mine] == [open_v.id]
    assert mine[0].price is None  # demo quotes never trigger a real alert

    await redis.set(cache_key(ins.instrument_id), quote(demo=False))
    facts = await view_facts(db, redis, now)
    mine = [f for f in facts if f.observation_id == open_v.id]
    assert mine[0].price == Decimal("23750")
    cands = view_invalidated(AlertFacts(now=now, market_open=True, views=tuple(mine)), P)
    stored = await store_alerts(db, cands, now=now, window=timedelta(minutes=30))
    assert [a.dedup_key for a in stored] == [f"view_invalidated:{open_v.id}"]
    # an hour later (outside the dedup window) the same view does not alert again
    later = now + timedelta(hours=1)
    facts = await view_facts(db, redis, later)
    mine = [f for f in facts if f.observation_id == open_v.id]
    assert mine[0].already_alerted
