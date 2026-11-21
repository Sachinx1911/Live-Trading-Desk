"""Tool-server units without a DB: rate limiter, bearer parsing, argument scrubbing, timeouts."""

from __future__ import annotations

import asyncio
from typing import Any

from ts_support import FAKE_JWT_SECRET, FAKE_SECRETS_KEY, fake_service

from protocols.catalogue import ToolCatalogue, ToolResult, ToolSpec
from protocols.context import ActionContext
from protocols.registry import ActionRegistry, NoArgs
from tool_server.ratelimit import RateLimiter
from tool_server.service import Caller, bearer


def test_token_bucket_refills() -> None:
    t = [0.0]
    rl = RateLimiter(2, clock=lambda: t[0])
    assert [rl.allow(1), rl.allow(1), rl.allow(1)] == [True, True, False]
    assert rl.allow(2)  # buckets are per token
    t[0] += 30.0  # half a minute = one token back at 2/min
    assert rl.allow(1) and not rl.allow(1)


def test_bearer_parsing() -> None:
    assert bearer("Bearer abc") == "abc"
    assert bearer("bearer  abc ") == "abc"
    assert bearer("Basic abc") is None
    assert bearer("Bearer ") is None
    assert bearer(None) is None


def test_scrub_redacts_secrets_tokens_and_sensitive_keys() -> None:
    svc = fake_service(ToolCatalogue(ActionRegistry()))
    presented = "ltd_presented_token_value_123456789"
    args: dict[str, Any] = {
        "symbols": ["NIFTY", presented, "ltd_someone_elses_token_abcdefgh"],
        "api_key": "K",
        "nested": {
            "Authorization": "Bearer x",
            "note": f"k={FAKE_SECRETS_KEY} j={FAKE_JWT_SECRET}",
        },
        "big": 2**70,
        "long": "x" * 1000,
    }
    out = svc.safe_args(args, presented)
    text = repr(out)
    for s in (presented, "ltd_someone_elses", FAKE_SECRETS_KEY, FAKE_JWT_SECRET):
        assert s not in text
    assert out["symbols"][0] == "NIFTY"
    assert out["api_key"] == "[redacted]" and out["nested"]["Authorization"] == "[redacted]"
    assert out["big"] == str(2**70)
    assert len(out["long"]) < 300
    assert svc.safe_args("not a dict", presented) == {"_invalid": "<str>"}
    huge = {f"k{i}": "v" * 150 for i in range(50)}
    assert svc.safe_args(huge, presented)["_truncated"] is True


def test_timeout_is_an_error_and_logged() -> None:
    reg = ActionRegistry()

    @reg.register("slow", "slow read", "green")
    async def slow(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
        await asyncio.sleep(5)
        return {}

    cat = ToolCatalogue(reg)
    cat.register(ToolSpec("slow", "slow", "Slow.", {}, ToolResult, timeout_s=0.05, registry=reg))
    svc = fake_service(cat)
    svc.tokens = {"t": Caller("ok", 1, 1, "t", "green")}
    out = asyncio.run(svc.call("t", "http", "slow", {}))
    assert (out.status, out.http_status, out.code) == ("error", 504, "timeout")
    assert svc.logged[-1]["status"] == "error"


def test_unexpected_exception_reports_type_only() -> None:
    reg = ActionRegistry()

    @reg.register("boom", "boom", "green")
    async def boom(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
        raise RuntimeError("postgresql://user:hunter2@db/x")

    cat = ToolCatalogue(reg)
    cat.register(ToolSpec("boom", "boom", "Boom.", {}, ToolResult, registry=reg))
    svc = fake_service(cat)
    svc.tokens = {"t": Caller("ok", 1, 1, "t", "green")}
    out = asyncio.run(svc.call("t", "http", "boom", {}))
    assert out.code == "internal" and out.message == "internal error (RuntimeError)"
    assert "hunter2" not in repr(svc.logged)


def test_result_without_provenance_is_an_error_not_an_answer() -> None:
    reg = ActionRegistry()

    @reg.register("bare", "no provenance", "green")
    async def bare(ctx: ActionContext, _: NoArgs) -> dict[str, Any]:
        return {"summary": "a number with no source", "value": 42}

    cat = ToolCatalogue(reg)
    cat.register(ToolSpec("bare", "bare", "Bare.", {}, ToolResult, registry=reg))
    svc = fake_service(cat)
    svc.tokens = {"t": Caller("ok", 1, 1, "t", "green")}
    out = asyncio.run(svc.call("t", "http", "bare", {}))
    assert out.status == "error" and out.result is None
