"""OpenAI adapter against recorded HTTP shapes (respx). No network."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from ai.llm import (
    LLMMessage,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMRequest,
    LLMTransportError,
    Usage,
)
from ai.llm.openai import OpenAIProvider, price_for

URL = "https://api.openai.com/v1/chat/completions"


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[LLMMessage(role="system", content="sys"), LLMMessage(role="user", content="hi")],
        schema_name="Answer",
        json_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        max_output_tokens=64,
    )


def _completion(
    content: str, *, model: str = "gpt-4o-mini-2024-07-18", **extra: Any
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    message.update(extra.pop("message", {}))
    return {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": extra.pop("finish", "stop")}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def _provider(**kw: Any) -> OpenAIProvider:
    return OpenAIProvider("sk-test", "gpt-4o-mini", retry_backoff_s=0.0, **kw)


@respx.mock
async def test_success_parses_content_usage_and_cost() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=_completion('{"x": 1}')))
    res = await _provider().complete_json(_request())
    assert res.text == '{"x": 1}'
    assert res.model == "gpt-4o-mini-2024-07-18"
    assert res.usage == Usage(120, 30)
    # 120 * 0.15/1M + 30 * 0.60/1M = 0.000018 + 0.000018
    assert res.cost_usd == Decimal("0.000036")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "gpt-4o-mini"
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["name"] == "Answer"
    assert sent["response_format"]["json_schema"]["strict"] is False
    assert sent["max_completion_tokens"] == 64
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"


@respx.mock
async def test_retries_429_then_succeeds() -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "slow down"}}),
            httpx.Response(200, json=_completion('{"x": 2}')),
        ]
    )
    res = await _provider(max_retries=2).complete_json(_request())
    assert res.text == '{"x": 2}' and route.call_count == 2


@respx.mock
async def test_persistent_5xx_raises_transport_error_after_retries() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(503, text="down"))
    with pytest.raises(LLMTransportError) as exc:
        await _provider(max_retries=2).complete_json(_request())
    assert exc.value.status == 503 and exc.value.retryable and route.call_count == 3


@respx.mock
async def test_4xx_is_not_retried() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad schema"}})
    )
    with pytest.raises(LLMTransportError, match="bad schema") as exc:
        await _provider().complete_json(_request())
    assert exc.value.status == 400 and not exc.value.retryable and route.call_count == 1


@respx.mock
async def test_network_failure_raises_transport_error() -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(LLMTransportError, match="unreachable") as exc:
        await _provider(max_retries=1).complete_json(_request())
    assert exc.value.retryable


@respx.mock
@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (_completion("", message={"content": None, "refusal": "I cannot"}), "refused"),
        (_completion('{"x":', finish="length"), "truncated"),
        (_completion("", message={"content": ""}), "empty"),
        ({"choices": []}, "shape"),
    ],
)
async def test_unusable_answers_raise_output_error(payload: dict[str, Any], match: str) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(LLMOutputError, match=match):
        await _provider().complete_json(_request())


async def test_missing_key_is_not_configured_and_never_calls_out() -> None:
    p = OpenAIProvider("", "gpt-4o-mini")
    assert not p.is_configured()
    with pytest.raises(LLMNotConfiguredError):
        await p.complete_json(_request())


def test_pricing_prefers_longest_prefix_and_reports_unknown() -> None:
    assert price_for("gpt-4.1-mini-2025-04-14") == price_for("gpt-4.1-mini")
    assert price_for("gpt-4.1") != price_for("gpt-4.1-mini")
    assert price_for("gpt-4o-mini") != price_for("gpt-4o")
    assert price_for("some-future-model") is None
    assert _provider().estimate_cost("some-future-model", Usage(10, 10)) is None
