"""OpenAI adapter: Chat Completions with `response_format = json_schema`.

Plain httpx, no SDK: the request surface we need is small, the retry/backoff policy must be
ours, and nothing here may ever log the API key. Prices are a static table; a model that is
not in it gets `cost_usd = None` (unknown is reported as unknown, never estimated).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from time import perf_counter
from typing import Any

import httpx

from ai.llm.provider import (
    LLMNotConfiguredError,
    LLMOutputError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTransportError,
    Usage,
)
from core.logging import get_logger

log = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})

# USD per 1M tokens (input, output), as published on openai.com/api/pricing.
# PRICING_AS_OF marks when this table was last checked; a stale table only affects the
# `cost_usd` figure stored in ai_calls, never the call itself. Dated model snapshots
# (e.g. gpt-4o-mini-2024-07-18) match their base name by longest prefix.
PRICING_AS_OF = "2025-06"
PRICING_USD_PER_1M: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "o4-mini": (Decimal("1.10"), Decimal("4.40")),
}
_MILLION = Decimal(1_000_000)


def price_for(model: str) -> tuple[Decimal, Decimal] | None:
    best: str | None = None
    for key in PRICING_USD_PER_1M:
        if model == key or model.startswith(key + "-"):
            if best is None or len(key) > len(best):
                best = key
    return PRICING_USD_PER_1M[best] if best else None


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        *,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 60.0,
        max_retries: int = 2,
        retry_backoff_s: float = 1.0,
    ) -> None:
        self._api_key = api_key
        self.default_model = model
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def estimate_cost(self, model: str, usage: Usage) -> Decimal | None:
        price = price_for(model)
        if price is None:
            return None
        cost = (usage.input_tokens * price[0] + usage.output_tokens * price[1]) / _MILLION
        return cost.quantize(Decimal("0.000001"))

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- request --------------------------------------------------------------------

    def _body(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_output_tokens,
            # strict=False on purpose: Pydantic schemas carry optional fields and formats that
            # strict mode rejects. Validation happens in ai.llm.calls with the same model.
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "schema": request.json_schema,
                    "strict": False,
                },
            },
        }

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        headers = {"authorization": f"Bearer {self._api_key}", "content-type": "application/json"}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.post(
                    f"{self.base_url}/chat/completions", json=body, headers=headers
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                log.warning("openai.transport_error", attempt=attempt, error=str(exc))
            else:
                if resp.status_code < 400:
                    return resp
                if resp.status_code not in RETRYABLE_STATUSES or attempt == self.max_retries:
                    raise LLMTransportError(
                        f"openai http {resp.status_code}: {_error_detail(resp)}",
                        status=resp.status_code,
                        retryable=resp.status_code in RETRYABLE_STATUSES,
                    )
                log.warning("openai.retryable_status", status=resp.status_code, attempt=attempt)
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_backoff_s * (2**attempt))
        raise LLMTransportError(f"openai unreachable: {last_exc}", retryable=True)

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        if not self.is_configured():
            raise LLMNotConfiguredError("OPENAI_API_KEY is not set")
        body = self._body(request)
        t0 = perf_counter()
        resp = await self._post(body)
        latency_ms = int((perf_counter() - t0) * 1000)
        data: dict[str, Any] = resp.json()
        try:
            choice = data["choices"][0]
            message = choice["message"]
            usage_raw = data["usage"]
            usage = Usage(int(usage_raw["prompt_tokens"]), int(usage_raw["completion_tokens"]))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMOutputError(f"openai response shape unexpected: {exc}") from exc
        if message.get("refusal"):
            raise LLMOutputError(f"model refused: {message['refusal']}")
        if choice.get("finish_reason") == "length":
            raise LLMOutputError("output truncated at max_output_tokens")
        content = message.get("content")
        if not content:
            raise LLMOutputError("empty content")
        model_used = str(data.get("model") or body["model"])
        return LLMResponse(
            text=content,
            model=model_used,
            usage=usage,
            latency_ms=latency_ms,
            cost_usd=self.estimate_cost(model_used, usage),
            raw=data,
        )


def _error_detail(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error") or {}
        return str(err.get("message") or resp.text[:200])
    except ValueError:
        return resp.text[:200]
