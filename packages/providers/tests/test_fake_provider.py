from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from core.models import Timeframe
from core.time import IST
from providers import registry
from providers.base import ConnectionState
from providers.fake import FakeMarketDataProvider

TODAY = date(2026, 11, 17)  # Tuesday


def _p(**kw: object) -> FakeMarketDataProvider:
    return FakeMarketDataProvider(seed=7, tick_interval=0, today=TODAY, **kw)


async def test_deterministic_same_seed() -> None:
    a, b = _p(), _p()
    s = datetime(2026, 11, 16, tzinfo=IST)
    e = datetime(2026, 11, 18, tzinfo=IST)
    ca = await a.get_candles(1, Timeframe.M5, s, e)
    cb = await b.get_candles(1, Timeframe.M5, s, e)
    assert [c.close for c in ca] == [c.close for c in cb]
    assert len(ca) == 2 * 75
    assert (await a.get_quotes([1]))[0].ltp == (await b.get_quotes([1]))[0].ltp


async def test_candles_valid_sorted_within_session() -> None:
    p = _p()
    s = datetime(2026, 11, 17, tzinfo=IST)
    cs = await p.get_candles(4, Timeframe.M1, s, s + timedelta(days=1))
    assert len(cs) == 375
    assert all(c.low <= c.open <= c.high and c.low <= c.close <= c.high for c in cs)
    assert [c.ts for c in cs] == sorted(c.ts for c in cs)
    first, last = cs[0].ts.astimezone(IST), cs[-1].ts.astimezone(IST)
    assert (first.hour, first.minute) == (9, 15)
    assert (last.hour, last.minute) == (15, 29)
    assert all(c.is_demo and c.provider_id == "fake" for c in cs)
    assert all(c.close % Decimal("0.05") == 0 for c in cs)


async def test_no_candles_on_weekend_and_daily_resample() -> None:
    p = _p()
    sat = datetime(2026, 11, 14, tzinfo=IST)
    assert await p.get_candles(1, Timeframe.M1, sat, sat + timedelta(days=2)) == []
    d = await p.get_candles(1, Timeframe.D1, sat, sat + timedelta(days=4))
    assert len(d) == 2  # Mon, Tue
    assert all(c.derived_from == Timeframe.M1 for c in d)
    with pytest.raises(ValueError):
        await p.get_candles(1, Timeframe.W1, sat, sat + timedelta(days=4))


async def test_stream_ticks_fast_and_demo() -> None:
    p = _p()
    await p.connect()
    ticks = []
    async for t in p.stream_ticks([1, 9]):
        ticks.append(t)
        if len(ticks) >= 10:
            break
    assert len(ticks) == 10
    assert {t.instrument_id for t in ticks} == {1, 9}
    assert all(t.is_demo and t.provider_id == "fake" and t.ts.tzinfo is not None for t in ticks)
    assert all(
        t.best_bid is not None and t.best_ask is not None and t.best_bid < t.best_ask for t in ticks
    )


async def test_health_transitions() -> None:
    p = _p()
    assert (await p.health()).state == ConnectionState.DISCONNECTED
    await p.connect()
    assert (await p.health()).state == ConnectionState.CONNECTED
    await p.disconnect()
    assert (await p.health()).state == ConnectionState.DISCONNECTED


async def test_universe_and_option_chain() -> None:
    p = _p()
    ins = await p.fetch_instruments()
    assert len(ins) == 15
    assert {i.symbol for i in ins} >= {"NIFTY", "BANKNIFTY", "INDIAVIX", "RELIANCE", "SBIN"}
    fut = next(i for i in ins if i.segment == "futures")
    assert fut.lot_size == 75 and fut.expiry is not None and fut.expiry.weekday() == 3
    chain = await p.get_option_chain(
        1, datetime.combine(fut.expiry, datetime.min.time(), tzinfo=UTC)
    )
    assert chain.is_demo and len(chain.rows) == 22
    ce = [r for r in chain.rows if r.option_type == "CE"]
    assert all(r.iv is not None and 12 <= r.iv <= 22 for r in chain.rows)
    assert all(r.delta is not None and 0 <= r.delta <= 1 for r in ce)
    assert all(r.gamma is not None and r.gamma >= 0 for r in chain.rows)
    assert all(r.vega is not None and r.vega >= 0 for r in chain.rows)
    assert all(r.theta is not None and r.theta <= 0 for r in chain.rows)


def test_registry() -> None:
    assert "fake" in registry.available()
    prov = registry.create("fake")
    assert prov.info.is_demo and prov.info.code == "fake"
    with pytest.raises(ValueError):
        registry.create("nope")


async def test_bind_mapping_translates_ids() -> None:
    p = FakeMarketDataProvider(seed=1, tick_interval=0)
    await p.connect()
    nifty = next(i for i in await p.fetch_instruments() if i.symbol == "NIFTY")
    p.bind_mapping({5001: "NIFTY"})
    quotes = await p.get_quotes([5001])
    assert [q.instrument_id for q in quotes] == [5001]
    internal = await p.get_quotes([nifty.instrument_id])
    assert internal[0].ltp == quotes[0].ltp
    ticks = []
    async for t in p.stream_ticks([5001]):
        ticks.append(t)
        if len(ticks) >= 3:
            break
    assert {t.instrument_id for t in ticks} == {5001}
