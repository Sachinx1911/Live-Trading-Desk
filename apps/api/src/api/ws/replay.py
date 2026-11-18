"""/ws/replay/{session_id}: control + event stream for one replay session.

Client → server: {"type": "play"|"pause"|"set_speed"|"step"|"seek", "x"?, "bars"?, "ts"?}
Server → client: binary JSON frames: bar, quote, signal, signal_rejected, order, fill,
position, trade, rewound, state. Auth via `?token=` (browsers cannot set WS headers).
"""

from __future__ import annotations

import asyncio
import contextlib

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.replay.manager import manager
from api.security import TokenError, decode_access_token
from api.state import AppState
from core.logging import get_logger

router = APIRouter()
log = get_logger("ws.replay")


@router.websocket("/ws/replay/{session_id}")
async def ws_replay(ws: WebSocket, session_id: str, token: str | None = None) -> None:
    state: AppState = ws.app.state.app
    if token is None:
        await ws.close(code=4401)
        return
    try:
        claims = decode_access_token(token, state.settings)
    except TokenError:
        await ws.close(code=4401)
        return
    sess = manager.get(session_id, int(claims["sub"]))
    if sess is None:
        await ws.close(code=4404)
        return
    await ws.accept()
    q = sess.subscribe()

    async def pump() -> None:
        while True:
            ev = await q.get()
            await ws.send_bytes(orjson.dumps(ev))

    task = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive_json()
            try:
                await sess.control(msg)
            except (ValueError, KeyError) as exc:
                await ws.send_bytes(orjson.dumps({"type": "error", "message": str(exc)}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws.replay_error", error=str(exc))
    finally:
        sess.unsubscribe(q)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
