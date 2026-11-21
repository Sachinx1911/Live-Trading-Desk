"""Tool server app (Mark 1 Stage 4.1): typed HTTP and MCP over one catalogue.

    GET  /healthz            no auth; liveness only, no data
    GET  /tools              catalogue callable with this token (JSON Schemas, levels, tiers)
    POST /tools/{name}       JSON object of arguments -> {ok, tool, call_id, result | error}
    *    /mcp                MCP streamable HTTP (stateless, JSON responses)

Run: `make tool-server` (binds TOOL_SERVER_HOST:TOOL_SERVER_PORT, default 127.0.0.1:8100).
No LLM runs here and there is no order path (CLAUDE.md rules 1-2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import orjson
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.routing import Route

from core.db import get_session_factory
from core.logging import configure_logging, get_logger
from core.secrets import SecretBox
from core.settings import Settings, get_settings
from protocols.catalogue import STAGE
from tool_server.mcp_app import McpGate, build_session_manager
from tool_server.service import LIST_TOOL, ToolService, bearer

log = get_logger(__name__)
VERSION = "0.1.0"


def default_service(settings: Settings) -> ToolService:
    try:
        box: SecretBox | None = SecretBox(settings.secrets_key.get_secret_value())
    except ValueError:
        box = None
    return ToolService(
        settings=settings,
        session_factory=get_session_factory(),
        redis=Redis.from_url(settings.redis_url, decode_responses=True),
        secret_box=box,
    )


def _json(status: int, body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


def create_app(service: ToolService | None = None, *, own_redis: bool | None = None) -> FastAPI:
    settings = service.settings if service is not None else get_settings()
    svc = service or default_service(settings)
    close_redis = own_redis if own_redis is not None else service is None
    manager = build_session_manager(svc)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_json)
        log.info(
            "tool_server.started",
            host=settings.tool_server_host,
            port=settings.tool_server_port,
            max_level=settings.tool_server_max_level,
            stage=STAGE,
        )
        async with manager.run():
            try:
                yield
            finally:
                if close_redis:
                    await svc.redis.aclose()
                log.info("tool_server.stopped")

    app = FastAPI(
        title="Live-Trading-Desk tool server",
        version=VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,  # the catalogue is served by GET /tools (authenticated)
    )
    app.state.service = svc

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "service": "tool_server", "stage": STAGE}

    @app.get("/tools")
    async def tools(request: Request) -> JSONResponse:
        presented = bearer(request.headers.get("authorization"))
        caller = await svc.authenticate(presented)
        if caller.status != "ok":
            out = await svc.log_refusal(
                presented=presented, caller=caller, transport="http", tool=LIST_TOOL
            )
            return _json(out.http_status, out.body(LIST_TOOL))
        return _json(200, {"ok": True, **svc.catalogue_view(caller)})

    @app.post("/tools/{name}")
    async def call(name: str, request: Request) -> JSONResponse:
        presented = bearer(request.headers.get("authorization"))
        raw = await request.body()
        args: Any
        if not raw.strip():
            args = {}
        else:
            try:
                args = orjson.loads(raw)
            except orjson.JSONDecodeError:
                args = "<invalid json>"
        out = await svc.call(presented, "http", name, args)
        return _json(out.http_status, out.body(name))

    app.router.routes.append(Route("/mcp", endpoint=McpGate(svc, manager)))
    return app


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "tool_server.main:create_app",
        factory=True,
        host=s.tool_server_host,
        port=s.tool_server_port,
        log_level=s.log_level.lower(),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
