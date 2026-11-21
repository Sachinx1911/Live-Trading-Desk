"""Property: no tool above the effective level (or not enabled in this stage) is callable, over
HTTP or MCP, whatever the caller sends; every attempt is logged. No DB: in-memory tokens."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import httpx
import mcp_types as types
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict
from ts_support import fake_service

from protocols.catalogue import (
    CATALOGUE,
    ToolCatalogue,
    ToolResult,
    ToolSpec,
    effective_level,
    level_allows,
)
from protocols.context import ActionContext
from protocols.registry import ActionRegistry
from tool_server.main import create_app
from tool_server.mcp_app import build_mcp_server
from tool_server.service import Caller

EXECUTED: list[str] = []
REG = ActionRegistry()


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int = 1


def _ok(name: str) -> dict[str, Any]:
    EXECUTED.append(name)
    return {"source": "test", "freshness": "none", "is_demo": False, "summary": name}


@REG.register("g_read", "green read", "green", Args)
async def g_read(ctx: ActionContext, a: Args) -> dict[str, Any]:
    return _ok("g_read")


@REG.register("y_change", "yellow change", "yellow")
async def y_change(ctx: ActionContext, _: Any) -> dict[str, Any]:
    return _ok("y_change")


@REG.register("y_paper", "yellow paper, later stage", "yellow")
async def y_paper(ctx: ActionContext, _: Any) -> dict[str, Any]:
    return _ok("y_paper")


@REG.register("r_money", "red: money", "red")
async def r_money(ctx: ActionContext, _: Any) -> dict[str, Any]:
    return _ok("r_money")


CAT = ToolCatalogue(REG)
CAT.register(ToolSpec("g_read", "g_read", "Read.", {"n": 1}, ToolResult, registry=REG))
CAT.register(ToolSpec("y_change", "y_change", "Change.", {}, ToolResult, registry=REG))
CAT.register(
    ToolSpec(
        "y_paper",
        "y_paper",
        "Paper change.",
        {},
        ToolResult,
        registry=REG,
        standing_permission=True,
        planned_stage=5,
    )
)

LEVELS = st.sampled_from(["green", "yellow"])
NAMES = st.one_of(
    st.sampled_from(["g_read", "y_change", "y_paper", "r_money", "place_order", "kill_switch_off"]),
    st.text(min_size=0, max_size=30),
)
JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=20),
    lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=8), c, max_size=3),
    max_leaves=8,
)
ARGS = st.one_of(st.dictionaries(st.text(max_size=8), JSON, max_size=4), JSON)
TOKEN = st.sampled_from(["good", "bad", ""])


def _allowed(name: str, server: str, token_level: str) -> bool:
    spec = CAT.get(name)
    return spec is not None and spec.callable_at(effective_level(server, token_level))


def test_red_actions_cannot_enter_a_catalogue() -> None:
    with pytest.raises(ValueError, match="red"):
        CAT.register(ToolSpec("r_money", "r_money", "Money.", {}, ToolResult, registry=REG))


@given(server=LEVELS, token=LEVELS, level=st.sampled_from(["green", "yellow", "red", "purple"]))
def test_level_algebra(server: str, token: str, level: str) -> None:
    eff = effective_level(server, token)
    assert eff in ("green", "yellow")
    assert level_allows(eff, level) == (
        level == "green" or (level == "yellow" and server == token == "yellow")
    )


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(server=LEVELS, token_level=LEVELS, who=TOKEN, name=NAMES, args=ARGS)
def test_http_never_runs_a_tool_above_the_effective_level(
    server: str, token_level: str, who: str, name: str, args: Any
) -> None:
    svc = fake_service(CAT, server)
    svc.tokens = {"good": Caller("ok", 1, 1, "t", token_level)}
    app = create_app(svc, own_redis=False)
    allowed = who == "good" and _allowed(name, server, token_level)

    async def go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
            headers = {"authorization": f"Bearer {who}"} if who else {}
            return await c.post(f"/tools/{quote(name, safe='')}", json=args, headers=headers)

    EXECUTED.clear()
    if "/" in name or not name.strip() or name in (".", ".."):
        return  # not a single path segment; the route itself is never reached
    r = asyncio.run(go())
    body = r.json()
    if not allowed:
        assert body["ok"] is False
        assert EXECUTED == []
        assert svc.logged and svc.logged[-1]["status"] == "refused"
    else:
        assert EXECUTED in ([], [name])  # [] only for bad arguments
        assert svc.logged[-1]["status"] in ("ok", "error")
    assert len(svc.logged) == 1


@settings(max_examples=120, deadline=None)
@given(server=LEVELS, token_level=LEVELS, who=TOKEN, name=NAMES, args=ARGS)
def test_mcp_never_lists_or_runs_a_tool_above_the_effective_level(
    server: str, token_level: str, who: str, name: str, args: Any
) -> None:
    svc = fake_service(CAT, server)
    svc.tokens = {"good": Caller("ok", 1, 1, "t", token_level)}
    srv = build_mcp_server(svc)
    req = SimpleNamespace(headers={"authorization": f"Bearer {who}"} if who else {})
    ctx = SimpleNamespace(request=req)
    list_h = srv.get_request_handler("tools/list")
    call_h = srv.get_request_handler("tools/call")
    assert list_h is not None and call_h is not None

    async def go() -> tuple[types.ListToolsResult, types.CallToolResult]:
        listed = await list_h.handler(ctx, None)  # type: ignore[arg-type]
        params = types.CallToolRequestParams(
            name=name, arguments=args if isinstance(args, dict) else None
        )
        called = await call_h.handler(ctx, params)  # type: ignore[arg-type]
        return listed, called

    EXECUTED.clear()
    listed, called = asyncio.run(go())
    eff = effective_level(server, token_level)
    for t in listed.tools:
        spec = CAT.get(t.name)
        assert spec is not None and spec.callable_at(eff) and who == "good"
    allowed = who == "good" and _allowed(name, server, token_level)
    if not allowed:
        assert called.is_error is True
        assert EXECUTED == []
        assert svc.logged[-1]["status"] == "refused"
        assert svc.logged[-1]["transport"] == "mcp"
    else:
        assert EXECUTED in ([], [name])


def test_real_catalogue_at_green_serves_green_only() -> None:
    svc = fake_service(CATALOGUE, "yellow")
    for token_level in ("green", "yellow"):
        names = {t.name for t in svc.visible(Caller("ok", 1, 1, "t", token_level))}
        assert names, "green tools must be listed"
        for n in names:
            spec = CATALOGUE.get(n)
            assert spec is not None and spec.level == "green" and spec.tier == "T0"
        # Stage 4: yellow tools exist in the catalogue but are not callable even at yellow.
        assert "kill_switch_on" not in names
        assert "stop_paper_strategies" not in names


def test_yellow_tool_refused_with_reason_and_logged() -> None:
    svc = fake_service(CATALOGUE, "green")
    svc.tokens = {"good": Caller("ok", 7, 1, "t", "yellow")}
    out = asyncio.run(svc.call("good", "http", "kill_switch_on", {"scope": "global"}))
    assert out.status == "refused" and out.http_status == 403
    assert "Stage 5" in (out.message or "")
    assert svc.logged[-1] == {
        "tool": "kill_switch_on",
        "transport": "http",
        "status": "refused",
        "code": "level_not_allowed",
        "args": {"scope": "global"},
        "token_id": 7,
        "error": out.message,
    }
