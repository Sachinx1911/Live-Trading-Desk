"""The governed call: budget check → provider → Pydantic validation → `ai_calls` record.

Every LLM use in the platform goes through `call_structured`. It never raises on an
*invalid* answer (the record says `validated=false` and the caller decides); it does raise
on budget exhaustion, missing configuration and transport failure, after recording them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError

from ai.llm.budget import DailyTokenBudget, TokenBudget
from ai.llm.provider import (
    LLMError,
    LLMMessage,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)
from ai.prompts import Prompt
from core.logging import get_logger

log = get_logger(__name__)

# Rough upper bound used only to reserve budget before a call; real usage replaces it.
CHARS_PER_TOKEN_ESTIMATE = 3


class AiCallEntry(BaseModel):
    """One row of `ai_calls` (ADR-009). Append-only; written even when the call failed."""

    agent: str
    provider: str
    model: str
    prompt_version: str
    schema_name: str
    schema_version: str
    input_refs: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None
    latency_ms: int
    validated: bool
    error: str | None
    job_id: UUID | None
    user_id: int | None
    payload_uri: str | None = None


class AiCallLogger(Protocol):
    async def record(self, entry: AiCallEntry) -> int | None: ...


class MemoryAiCallLogger:
    """In-process logger for tests and dry runs."""

    def __init__(self) -> None:
        self.entries: list[AiCallEntry] = []

    async def record(self, entry: AiCallEntry) -> int | None:
        self.entries.append(entry)
        return len(self.entries)


@dataclass
class CallResult[T: BaseModel]:
    output: T | None
    call_id: int | None
    response: LLMResponse | None
    entry: AiCallEntry

    @property
    def validated(self) -> bool:
        return self.output is not None

    def require(self) -> T:
        if self.output is None:
            raise LLMOutputError(self.entry.error or "model output failed validation")
        return self.output


def estimate_tokens(messages: Sequence[LLMMessage]) -> int:
    return sum(len(m.content) for m in messages) // CHARS_PER_TOKEN_ESTIMATE + 1


async def call_structured[T: BaseModel](
    provider: LLMProvider,
    *,
    agent: str,
    prompt: Prompt,
    user_messages: Sequence[LLMMessage] | str,
    output_model: type[T],
    input_refs: Mapping[str, Any] | None = None,
    logger: AiCallLogger | None = None,
    budget: TokenBudget | None = None,
    daily: DailyTokenBudget | None = None,
    job_id: UUID | None = None,
    user_id: int | None = None,
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
    model: str | None = None,
    schema_version: str = "1",
) -> CallResult[T]:
    if not provider.is_configured():
        raise LLMNotConfiguredError(f"{provider.name} provider is not configured")

    msgs: list[LLMMessage] = [LLMMessage(role="system", content=prompt.system)]
    if isinstance(user_messages, str):
        msgs.append(LLMMessage(role="user", content=user_messages))
    else:
        msgs.extend(user_messages)

    reserve = estimate_tokens(msgs) + max_output_tokens
    if budget is not None:
        budget.check(reserve)
    if daily is not None:
        await daily.check(reserve)

    request = LLMRequest(
        messages=msgs,
        schema_name=output_model.__name__,
        json_schema=output_model.model_json_schema(),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        model=model,
    )
    refs = dict(input_refs or {})
    base: dict[str, Any] = {
        "agent": agent,
        "provider": provider.name,
        "model": model or provider.default_model,
        "prompt_version": f"{prompt.name}@{prompt.version}",
        "schema_name": output_model.__name__,
        "schema_version": schema_version,
        "input_refs": refs,
        "job_id": job_id,
        "user_id": user_id,
    }

    try:
        response = await provider.complete_json(request)
    except LLMError as exc:
        entry = AiCallEntry(
            **base,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            latency_ms=0,
            validated=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        if logger is not None:
            await logger.record(entry)
        log.warning("ai.call_failed", agent=agent, error=str(exc))
        raise

    if budget is not None:
        budget.consume(response.usage)
    if daily is not None:
        await daily.consume(response.usage)

    output: T | None
    error: str | None
    try:
        output = output_model.model_validate_json(response.text)
        error = None
    except ValidationError as exc:
        output = None
        error = f"ValidationError: {exc.error_count()} error(s): {exc.errors()[:3]}"
        log.warning("ai.output_invalid", agent=agent, schema=output_model.__name__)

    entry = AiCallEntry(
        **{**base, "model": response.model},
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
        validated=output is not None,
        error=error,
    )
    call_id = await logger.record(entry) if logger is not None else None
    log.info(
        "ai.call",
        agent=agent,
        model=response.model,
        tokens=response.usage.total,
        validated=output is not None,
        call_id=call_id,
    )
    return CallResult(output=output, call_id=call_id, response=response, entry=entry)
