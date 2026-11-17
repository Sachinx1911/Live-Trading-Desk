"""/ws/market: fan-out of the collector's Redis channels to browsers.

Client → server: {"action": "subscribe", "instrument_ids": [..]} / {"action": "unsubscribe", ...}
Server → client: {"type": "quote", ...Quote} and {"type": "candle", ...Candle}, plus
{"type": "status", "collector": {...}} every 5 s so the UI can show Disconnected honestly.
Auth: access token as `?token=` query param (browsers cannot set WS headers).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from api.security import TokenError, decode_access_token
from api.state import AppState
from core.logging import get_logger

router = APIRouter()
log = get_logger("ws.market")

CHANNELS = ("market.tick", "market.candle")


async def _pump(redis: Redis, ws: WebSocket, subs: set[int]) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe(*CHANNELS)
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            data: dict[str, Any] = orjson.loads(msg["data"])
            if data.get("instrument_id") not in subs:
                continue
            kind = "quote" if msg["channel"] in (b"market.tick", "market.tick") else "candle"
            await ws.send_bytes(orjson.dumps({"type": kind, **data}))
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(*CHANNELS)
            await pubsub.aclose()  # type: ignore[no-untyped-call]


async def _status(redis: Redis, ws: WebSocket) -> None:
    while True:
        raw = await redis.get("collector:health")
        payload = {"type": "status", "collector": orjson.loads(raw) if raw else None}
        await ws.send_bytes(orjson.dumps(payload))
        await asyncio.sleep(5)


@router.websocket("/ws/market")
async def ws_market(ws: WebSocket, token: str | None = None) -> None:
    state: AppState = ws.app.state.app
    if token is None:
        await ws.close(code=4401)
        return
    try:
        decode_access_token(token, state.settings)
    except TokenError:
        await ws.close(code=4401)
        return
    await ws.accept()
    subs: set[int] = set()
    tasks = [
        asyncio.create_task(_pump(state.redis, ws, subs)),
        asyncio.create_task(_status(state.redis, ws)),
    ]
    try:
        while True:
            msg = await ws.receive_json()
            ids = {int(i) for i in msg.get("instrument_ids", [])}
            if msg.get("action") == "subscribe":
                subs |= ids
            elif msg.get("action") == "unsubscribe":
                subs -= ids
            await ws.send_bytes(
                orjson.dumps({"type": "subscribed", "instrument_ids": sorted(subs)})
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws.market_error", error=str(exc))
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
