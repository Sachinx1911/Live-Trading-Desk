import asyncio
import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from providers.upstox.client import UpstoxRest
from providers.upstox.feed import UpstoxFeed
from providers.upstox.mapping import map_feed_response

pb: Any = importlib.import_module("providers.upstox.proto.MarketDataFeedV3_pb2")
NOW = datetime(2025, 11, 17, 4, 0, tzinfo=UTC)


def _full_feed_msg() -> bytes:
    msg = pb.FeedResponse()
    msg.type = pb.Type.live_feed
    msg.currentTs = 1763354100123
    f = msg.feeds["NSE_FO|53001"]
    m = f.fullFeed.marketFF
    m.ltpc.ltp = 25990.5
    m.ltpc.ltt = 1763354100000
    m.ltpc.ltq = 75
    m.ltpc.cp = 25900.0
    q = m.marketLevel.bidAskQuote.add()
    q.bidQ, q.bidP, q.askQ, q.askP = 150, 25990.0, 225, 25991.0
    q2 = m.marketLevel.bidAskQuote.add()
    q2.bidQ, q2.bidP, q2.askQ, q2.askP = 300, 25989.5, 75, 25991.5
    m.vtt = 1234567
    m.oi = 9876543.0
    idx = msg.feeds["NSE_INDEX|Nifty 50"].fullFeed.indexFF
    idx.ltpc.ltp = 25955.0
    idx.ltpc.ltt = 1763354100000
    eq = msg.feeds["NSE_EQ|INE002A01018"].ltpc
    eq.ltp = 1490.2
    eq.ltt = 1763354099000
    eq.ltq = 10
    return bytes(msg.SerializeToString())


def test_protobuf_roundtrip_to_ticks() -> None:
    msg = pb.FeedResponse()
    msg.ParseFromString(_full_feed_msg())
    ids = {"NSE_FO|53001": 5, "NSE_INDEX|Nifty 50": 1, "NSE_EQ|INE002A01018": 11}
    ticks = {t.instrument_id: t for t in map_feed_response(msg, ids, NOW)}
    fut = ticks[5]
    assert fut.ltp == Decimal("25990.5") and fut.ltq == 75
    assert fut.volume == 1234567 and fut.oi == 9876543
    assert [b.price for b in fut.bids] == [Decimal("25990.0"), Decimal("25989.5")]
    assert fut.asks[0].quantity == 225
    assert fut.ts == datetime.fromtimestamp(1763354100, tz=UTC)
    assert fut.provider_ts == datetime.fromtimestamp(1763354100.123, tz=UTC)
    assert fut.provider_id == "upstox" and fut.is_demo is False
    assert ticks[1].ltp == Decimal("25955.0") and ticks[1].bids == ()
    assert ticks[11].ltq == 10
    # unknown keys are dropped
    assert map_feed_response(msg, {"NSE_FO|53001": 5}, NOW)[0].instrument_id == 5


class _FakeWs:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = frames
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    def __aiter__(self):  # type: ignore[no-untyped-def]
        return self._gen()

    async def _gen(self):  # type: ignore[no-untyped-def]
        for f in self.frames:
            yield f


@pytest.mark.asyncio
async def test_feed_authorizes_subscribes_decodes_and_reconnects() -> None:
    authorize_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal authorize_calls
        assert request.headers["Authorization"] == "Bearer tok"
        authorize_calls += 1
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"authorized_redirect_uri": "wss://x/y"},
            },
        )

    rest = UpstoxRest(lambda: "tok", transport=httpx.MockTransport(handler))
    first_ws = _FakeWs([_full_feed_msg()])
    sockets = [first_ws, _FakeWs([_full_feed_msg()])]
    feed = UpstoxFeed(
        rest,
        ["NSE_FO|53001"],
        {"NSE_FO|53001": 5},
        connect=lambda url: _connect(url, sockets),
        max_backoff=0.01,
    )
    got = []
    async for tick in feed:
        got.append(tick)
        if len(got) == 2:
            feed.stop()
    assert authorize_calls == 2  # single-use URL → re-authorised on reconnect
    assert feed.stats.reconnects_today == 1
    sub = json.loads(first_ws.sent[0])
    assert sub["method"] == "sub" and sub["data"]["mode"] == "full"
    assert sub["data"]["instrumentKeys"] == ["NSE_FO|53001"]
    assert feed.stats.last_message_at is not None and feed.stats.latency_ms is not None
    await rest.aclose()


async def _connect(url: str, sockets: list[_FakeWs]) -> _FakeWs:
    assert url == "wss://x/y"
    await asyncio.sleep(0)
    return sockets.pop(0)
