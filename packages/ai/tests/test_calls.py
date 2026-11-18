"""The governed call: budget → provider → validation → ai_calls entry."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel, Field

from ai.llm import (
    BudgetExceededError,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTransportError,
    MemoryAiCallLogger,
    TokenBudget,
    Usage,
    call_structured,
)
from ai.prompts import Prompt

PROMPT = Prompt(name="unit", version="3", system="You answer with JSON.")


class Answer(BaseModel):
    value: int = Field(ge=0)
    note: str


class FakeProvider(LLMProvider):
    name = "fake"
    default_model = "fake-1"

    def __init__(self, text: str | Exception, configured: bool = True) -> None:
        self.text = text
        self.configured = configured
        self.requests: list[LLMRequest] = []

    def is_configured(self) -> bool:
        return self.configured

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if isinstance(self.text, Exception):
            raise self.text
        return LLMResponse(
            text=self.text,
            model="fake-1-2026",
            usage=Usage(100, 20),
            latency_ms=12,
            cost_usd=Decimal("0.000123"),
        )


async def test_valid_answer_is_parsed_and_logged() -> None:
    provider = FakeProvider('{"value": 7, "note": "ok"}')
    logger = MemoryAiCallLogger()
    budget = TokenBudget(limit=10_000)
    job = uuid4()
    res = await call_structured(
        provider,
        agent="translator",
        prompt=PROMPT,
        user_messages="EMA 9 crosses EMA 21",
        output_model=Answer,
        input_refs={"strategy_version_id": 5},
        logger=logger,
        budget=budget,
        job_id=job,
        user_id=1,
        max_output_tokens=500,
    )
    assert res.validated and res.require() == Answer(value=7, note="ok")
    assert res.call_id == 1 and budget.used == 120 and budget.calls == 1
    req = provider.requests[0]
    assert req.messages[0].role == "system" and req.messages[0].content == PROMPT.system
    assert req.messages[1].content == "EMA 9 crosses EMA 21"
    assert req.schema_name == "Answer" and "value" in req.json_schema["properties"]
    e = logger.entries[0]
    assert e.agent == "translator" and e.provider == "fake" and e.model == "fake-1-2026"
    assert e.prompt_version == "unit@3" and e.schema_name == "Answer" and e.schema_version == "1"
    assert e.input_refs == {"strategy_version_id": 5} and e.job_id == job and e.user_id == 1
    assert (e.input_tokens, e.output_tokens, e.latency_ms) == (100, 20, 12)
    assert e.cost_usd == Decimal("0.000123") and e.validated and e.error is None


async def test_invalid_answer_is_logged_not_raised() -> None:
    provider = FakeProvider('{"value": -1, "note": 3}')
    logger = MemoryAiCallLogger()
    res = await call_structured(
        provider, agent="translator", prompt=PROMPT, user_messages="x", output_model=Answer,
        logger=logger,
    )  # fmt: skip
    assert not res.validated and res.output is None
    with pytest.raises(LLMOutputError, match="ValidationError"):
        res.require()
    e = logger.entries[0]
    assert not e.validated and e.error and "ValidationError" in e.error
    assert e.input_tokens == 100  # tokens were spent and are accounted for


async def test_budget_exceeded_refuses_before_calling_provider() -> None:
    provider = FakeProvider('{"value": 1, "note": ""}')
    budget = TokenBudget(limit=100)
    with pytest.raises(BudgetExceededError):
        await call_structured(
            provider, agent="researcher", prompt=PROMPT, user_messages="x", output_model=Answer,
            budget=budget, max_output_tokens=200,
        )  # fmt: skip
    assert provider.requests == [] and budget.used == 0


async def test_not_configured_provider_raises_without_logging() -> None:
    provider = FakeProvider('{"value": 1, "note": ""}', configured=False)
    logger = MemoryAiCallLogger()
    with pytest.raises(LLMNotConfiguredError):
        await call_structured(
            provider, agent="analyst", prompt=PROMPT, user_messages="x", output_model=Answer,
            logger=logger,
        )  # fmt: skip
    assert logger.entries == []


async def test_transport_failure_is_logged_then_reraised() -> None:
    provider = FakeProvider(LLMTransportError("openai http 503: down", status=503, retryable=True))
    logger = MemoryAiCallLogger()
    budget = TokenBudget(limit=10_000)
    with pytest.raises(LLMTransportError):
        await call_structured(
            provider, agent="reviewer", prompt=PROMPT, user_messages="x", output_model=Answer,
            logger=logger, budget=budget,
        )  # fmt: skip
    e = logger.entries[0]
    assert not e.validated and e.error and "503" in e.error
    assert (e.input_tokens, e.output_tokens) == (0, 0) and budget.used == 0


async def test_user_messages_can_be_a_conversation() -> None:
    from ai.llm import LLMMessage

    provider = FakeProvider('{"value": 1, "note": "n"}')
    convo = [
        LLMMessage(role="user", content="first"),
        LLMMessage(role="assistant", content='{"value": 0, "note": "?"}'),
        LLMMessage(role="user", content="second"),
    ]
    await call_structured(
        provider, agent="translator", prompt=PROMPT, user_messages=convo, output_model=Answer,
        model="fake-override",
    )  # fmt: skip
    req = provider.requests[0]
    assert [m.role for m in req.messages] == ["system", "user", "assistant", "user"]
    assert req.model == "fake-override"
