"""MCP transport (official `mcp` SDK, low-level server, streamable HTTP at /mcp).

Lists and calls the same catalogue as the typed HTTP routes, with the same JSON Schemas,
through the same `ToolService.call` (auth, level gate, rate limit, timeout, tool_calls log).
Every HTTP request to /mcp must carry `Authorization: Bearer <token>`; a missing, unknown or
revoked token is refused with 401 before the MCP layer sees the request, and logged.
"""

from __future__ import annotations

from typing import Any

import mcp_types as types
import orjson
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from tool_server.service import CONNECT_TOOL, ToolService, bearer

SERVER_NAME = "live-trading-desk"
INSTRUCTIONS = (
    "Live-Trading-Desk trading tools (domain 'trading'). Read-only in Stage 4. Every result "
    "carries source, freshness and is_demo: repeat them, never present demo or stale data as "
    "live. No tool places, modifies or cancels an order."
)


def _presented(ctx: ServerRequestContext[Any, Any]) -> str | None:
    req = ctx.request
    headers = getattr(req, "headers", None)
    return bearer(headers.get("authorization")) if headers is not None else None


def build_mcp_server(service: ToolService) -> Server[Any]:
    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        caller = await service.authenticate(_presented(ctx))
        tools = [
            types.Tool(
                name=t.name,
                title=t.name.replace("_", " "),
                description=t.description,
                input_schema=t.input_schema(),
                output_schema=t.output_schema(),
                annotations=types.ToolAnnotations(
                    read_only_hint=t.level == "green" and not t.writes,
                    destructive_hint=False,
                    idempotent_hint=t.level == "green",
                    open_world_hint=False,
                ),
                meta={
                    "level": t.level,
                    "tier": t.tier,
                    "domain": t.domain,
                    "timeout_s": t.timeout_s,
                },
            )
            for t in service.visible(caller)
        ]
        return types.ListToolsResult(tools=tools)

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        out = await service.call(_presented(ctx), "mcp", params.name, params.arguments or {})
        body = out.body(params.name)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=orjson.dumps(body).decode())],
            structured_content=out.result if out.status == "ok" else None,
            is_error=out.status != "ok",
        )

    return Server(
        SERVER_NAME,
        version="0.1.0",
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def security_for(host: str, port: int) -> TransportSecuritySettings:
    """DNS-rebinding protection: only the configured host (plus loopback) may be addressed."""
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", "::"):  # noqa: S104
        hosts.append(f"{host}:*")
    if host in ("0.0.0.0", "::"):  # noqa: S104 - owner chose every interface; the token still guards
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    origins = [f"http://{h}" for h in hosts]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def build_session_manager(service: ToolService) -> StreamableHTTPSessionManager:
    s = service.settings
    return StreamableHTTPSessionManager(
        app=build_mcp_server(service),
        json_response=True,
        stateless=True,
        security_settings=security_for(s.tool_server_host, s.tool_server_port),
    )


class McpGate:
    """ASGI wrapper: bearer token required on every /mcp request; refusals are logged."""

    def __init__(self, service: ToolService, manager: StreamableHTTPSessionManager) -> None:
        self.service = service
        self.manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.manager.asgi_app(scope, receive, send)
            return
        raw = dict(scope.get("headers") or []).get(b"authorization")
        presented = bearer(raw.decode("latin-1") if raw else None)
        caller = await self.service.authenticate(presented)
        if caller.status != "ok":
            out = await self.service.log_refusal(
                presented=presented, caller=caller, transport="mcp", tool=CONNECT_TOOL
            )
            body = orjson.dumps(out.body(CONNECT_TOOL))
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.manager.asgi_app(scope, receive, send)
