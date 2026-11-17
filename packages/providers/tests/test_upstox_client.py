import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from core.models import Timeframe
from core.time import IST
from providers import registry
from providers.base import ConnectionState
from providers.upstox.auth import UpstoxAuth, token_expiry_after
from providers.upstox.client import UpstoxRest
from providers.upstox.errors import UpstoxAuthError, UpstoxError
from providers.upstox.provider import UpstoxMarketDataProvider
from providers.upstox.ratelimit import MultiWindowRateLimiter, Window

FIX = Path(__file__).parent / "fixtures" / "upstox"


def test_login_url_and_expiry() -> None:
    a = UpstoxAuth("cid", "sec", "http://localhost/cb")
    url = a.login_url("abc")
    assert url.startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=cid" in url and "state=abc" in url and "response_type=code" in url
    issued = datetime(2025, 11, 17, 10, 0, tzinfo=IST)
    exp = token_expiry_after(issued).astimezone(IST)
    assert (exp.date(), exp.hour, exp.minute) == (datetime(2025, 11, 18).date(), 3, 30)


@pytest.mark.asyncio
async def test_exchange_code_posts_form() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST" and req.url.path == "/v2/login/authorization/token"
        body = req.content.decode()
        assert "grant_type=authorization_code" in body and "code=xyz" in body
        return httpx.Response(200, json={"access_token": "tok123", "email": "x@y.z"})

    a = UpstoxAuth("cid", "sec", "http://localhost/cb", transport=httpx.MockTransport(handler))
    token, exp = await a.exchange_code("xyz")
    assert token == "tok123" and exp.tzinfo is not None and exp > datetime.now(UTC)


@pytest.mark.asyncio
async def test_exchange_code_rejected() -> None:
    a = UpstoxAuth(
        "cid",
        "sec",
        "cb",
        transport=httpx.MockTransport(lambda r: httpx.Response(400, json={})),
    )
    with pytest.raises(UpstoxAuthError):
        await a.exchange_code("bad")


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_window_full() -> None:
    t = [0.0]
    lim = MultiWindowRateLimiter((Window(2, 1.0),), clock=lambda: t[0])
    await lim.acquire()
    await lim.acquire()
    assert lim.would_wait() == pytest.approx(1.0)
    t[0] = 1.0
    assert lim.would_wait() == 0.0
    await lim.acquire()


@pytest.mark.asyncio
async def test_rest_errors_and_retries() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if req.url.path == "/unauth":
            return httpx.Response(401, json={})
        if req.url.path == "/flaky":
            return (
                httpx.Response(503)
                if calls["n"] < 3
                else httpx.Response(200, json={"status": "success", "data": 1})
            )
        return httpx.Response(400, json={"status": "error", "errors": [{"errorCode": "UDAPI1148"}]})

    rest = UpstoxRest(lambda: "tok", transport=httpx.MockTransport(handler), max_attempts=3)
    with pytest.raises(UpstoxAuthError):
        await rest.get_json("/unauth")
    calls["n"] = 0
    assert (await rest.get_json("/flaky"))["data"] == 1 and calls["n"] == 3
    with pytest.raises(UpstoxError) as ei:
        await rest.get_json("/bad")
    assert ei.value.code == "UDAPI1148"
    no_token = UpstoxRest(lambda: None, transport=httpx.MockTransport(handler))
    with pytest.raises(UpstoxAuthError):
        await no_token.get_json("/x")
    await rest.aclose()


def _provider(handler, token="tok", expiry=None):  # type: ignore[no-untyped-def]
    return UpstoxMarketDataProvider(
        lambda: token,
        token_expiry_getter=lambda: expiry,
        transport=httpx.MockTransport(handler),
        instruments_url="https://assets.test/NSE.json",
    )


@pytest.mark.asyncio
async def test_provider_instruments_quotes_candles_chain() -> None:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        p = req.url.path
        if p.endswith("NSE.json"):
            return httpx.Response(200, content=(FIX / "instruments_nse.json").read_bytes())
        if p == "/v2/market-quote/quotes":
            return httpx.Response(200, json=json.loads((FIX / "quotes.json").read_text()))
        if p.startswith("/v3/historical-candle/intraday/"):
            return httpx.Response(200, json=json.loads((FIX / "intraday_5m.json").read_text()))
        if p.startswith("/v3/historical-candle/"):
            return httpx.Response(200, json=json.loads((FIX / "historical_5m.json").read_text()))
        if p == "/v2/option/chain":
            return httpx.Response(200, json=json.loads((FIX / "option_chain.json").read_text()))
        return httpx.Response(404)

    prov = _provider(handler)
    await prov.connect()
    assert (await prov.health()).state is ConnectionState.CONNECTED
    insts = await prov.fetch_instruments()
    nifty = next(i for i in insts if i.symbol == "NIFTY")
    rel = next(i for i in insts if i.symbol == "RELIANCE")
    ce = next(i for i in insts if i.symbol == "NIFTY26000CE20NOV25")
    pe = next(i for i in insts if i.symbol == "NIFTY26000PE20NOV25")
    # bind DB ids as market_data.sync would
    prov.bind_mapping(
        {
            1: "NSE_INDEX|Nifty 50",
            11: "NSE_EQ|INE002A01018",
            21: "NSE_FO|40001",
            22: "NSE_FO|40002",
        }
    )
    assert prov.instrument_key(1) == "NSE_INDEX|Nifty 50"
    assert prov.provider_key_for(nifty) == "NSE_INDEX|Nifty 50"
    assert prov.instrument_key(rel.instrument_id) == "NSE_EQ|INE002A01018"
    quotes = await prov.get_quotes([1, 11])
    assert {q.instrument_id for q in quotes} == {1, 11}
    start = datetime(2025, 11, 14, 3, 45, tzinfo=UTC)
    end = datetime(2025, 11, 14, 10, 0, tzinfo=UTC)
    candles = await prov.get_candles(1, Timeframe.M5, start, end)
    assert len(candles) == 3 and candles[0].ts == start
    assert any(
        "/v3/historical-candle/NSE_INDEX|Nifty%2050/minutes/5/2025-11-14/2025-11-14" in u
        or "minutes/5/2025-11-14/2025-11-14" in u
        for u in seen
    )
    snap = await prov.get_option_chain(1, datetime(2025, 11, 20, tzinfo=UTC))
    assert {r.instrument_id for r in snap.rows} == {21, 22}
    assert ce.strike == pe.strike
    await prov.disconnect()


@pytest.mark.asyncio
async def test_provider_health_auth_required_and_registry() -> None:
    prov = _provider(lambda r: httpx.Response(500), token=None)
    with pytest.raises(UpstoxAuthError):
        await prov.connect()
    assert (await prov.health()).state is ConnectionState.AUTH_REQUIRED
    expired = _provider(
        lambda r: httpx.Response(500),
        token="tok",
        expiry=datetime(2020, 1, 1, tzinfo=UTC),
    )
    assert (await expired.health()).state is ConnectionState.AUTH_REQUIRED
    assert "upstox" in registry.available()
    inst = registry.create("upstox")
    assert inst.info.code == "upstox" and inst.info.is_demo is False
    with pytest.raises(UpstoxError):
        inst.instrument_key(42)
