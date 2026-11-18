"""Upstox v3 market data WebSocket: authorize, connect, subscribe, decode, reconnect."""

from __future__ import annotations

import asyncio
import importlib
import json
import random
import ssl
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

import certifi
import websockets
from websockets.exceptions import ConnectionClosed

from core.logging import get_logger
from core.models import Tick
from core.time import utcnow
from providers.upstox.client import UpstoxRest
from providers.upstox.errors import UpstoxAuthError
from providers.upstox.mapping import map_feed_response

log = get_logger(__name__)

# Imported dynamically so type checkers never analyse the generated protobuf stubs.
pb: Any = importlib.import_module("providers.upstox.proto.MarketDataFeedV3_pb2")

AUTHORIZE_PATH = "/v3/feed/market-data-feed/authorize"
MODES = frozenset({"ltpc", "option_greeks", "full", "full_d30"})

ConnectFn = Callable[[str], Awaitable[object]]


class FeedStats:
    def __init__(self) -> None:
        self.last_message_at: datetime | None = None
        self.latency_ms: float | None = None
        self.reconnects_today: int = 0
        self.connected: bool = False
        self.last_error: str | None = None


class UpstoxFeed:
    """Async iterator of canonical ticks. Reconnects with backoff, re-authorising each time."""

    def __init__(
        self,
        rest: UpstoxRest,
        instrument_keys: Sequence[str],
        id_by_key: Mapping[str, int],
        *,
        mode: str = "full",
        stats: FeedStats | None = None,
        max_backoff: float = 30.0,
        connect: ConnectFn | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown feed mode {mode!r}")
        self._rest = rest
        self._keys = list(instrument_keys)
        self._id_by_key = dict(id_by_key)
        self._mode = mode
        self.stats = stats or FeedStats()
        self._max_backoff = max_backoff
        self._connect = connect or self._default_connect
        self._stop = asyncio.Event()

    @staticmethod
    async def _default_connect(url: str) -> object:
        # python.org builds on macOS ship without system CA certs; use certifi like httpx does.
        ctx = ssl.create_default_context(cafile=certifi.where())
        return await websockets.connect(url, max_size=2**22, ping_interval=None, ssl=ctx)

    async def authorized_url(self) -> str:
        body = await self._rest.get_json(AUTHORIZE_PATH)
        url = (body.get("data") or {}).get("authorized_redirect_uri")
        if not url:
            raise UpstoxAuthError("feed authorize returned no authorized_redirect_uri")
        return str(url)

    def subscribe_message(self) -> bytes:
        return json.dumps(
            {
                "guid": uuid.uuid4().hex,
                "method": "sub",
                "data": {"mode": self._mode, "instrumentKeys": self._keys},
            }
        ).encode()

    def stop(self) -> None:
        self._stop.set()

    async def __aiter__(self) -> AsyncIterator[Tick]:
        backoff = 1.0
        first = True
        while not self._stop.is_set():
            try:
                url = await self.authorized_url()
                ws = await self._connect(url)
                if not first:
                    self.stats.reconnects_today += 1
                first = False
                self.stats.connected = True
                self.stats.last_error = None
                backoff = 1.0
                await ws.send(self.subscribe_message())  # type: ignore[attr-defined]
                log.info("upstox.feed.connected", keys=len(self._keys), mode=self._mode)
                async for raw in ws:  # type: ignore[attr-defined]
                    if self._stop.is_set():
                        break
                    if not isinstance(raw, bytes | bytearray):
                        continue
                    msg = pb.FeedResponse()
                    msg.ParseFromString(bytes(raw))
                    now = utcnow()
                    self.stats.last_message_at = now
                    if msg.currentTs:
                        self.stats.latency_ms = max(
                            0.0, now.timestamp() * 1000 - float(msg.currentTs)
                        )
                    for tick in map_feed_response(msg, self._id_by_key, now):
                        yield tick
                self.stats.connected = False
                if self._stop.is_set():
                    break
                log.warning("upstox.feed.closed")
            except UpstoxAuthError:
                self.stats.connected = False
                self.stats.last_error = "auth_required"
                log.warning("upstox.feed.auth_required")
                raise
            except (TimeoutError, ConnectionClosed, OSError) as exc:
                self.stats.connected = False
                self.stats.last_error = str(exc)
                log.warning("upstox.feed.error", error=str(exc))
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff + random.uniform(0, backoff / 4))  # noqa: S311
            backoff = min(self._max_backoff, backoff * 2)
