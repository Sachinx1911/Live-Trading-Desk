"""`LLMProvider`: the only way this platform talks to a language model (ADR-009).

A provider turns a list of messages plus a JSON Schema into raw JSON text and usage
numbers. It does not validate, log or budget; `ai.llm.calls` does that so every provider
(OpenAI today; Anthropic, Gemini, local later) gets identical governance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["system", "user", "assistant"]


class LLMError(Exception):
    """Base class for everything the LLM boundary can raise."""


class LLMNotConfiguredError(LLMError):
    """No API key / provider configured. Callers show "AI not configured", never a fake answer."""


class LLMTransportError(LLMError):
    """HTTP / network failure after retries. `status` is the last HTTP status when known."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class LLMOutputError(LLMError):
    """The model answered but not with usable JSON (refusal, empty, truncated)."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    """One structured-output request. `json_schema` is what the model must answer with;
    the caller validates the answer against the Pydantic model it came from."""

    model_config = ConfigDict(frozen=True)

    messages: list[LLMMessage] = Field(min_length=1)
    schema_name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    json_schema: dict[str, Any]
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=32_000)
    model: str | None = None  # override the provider default for this call only


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    text: str  # raw JSON text exactly as returned
    model: str  # the model that actually answered (providers may resolve aliases)
    usage: Usage
    latency_ms: int
    cost_usd: Decimal | None  # None when the price list does not know the model: never guessed
    raw: dict[str, Any] = Field(default_factory=dict)  # provider payload for payload_uri archival


class LLMProvider(ABC):
    """Implement `complete_json`; everything else has a sensible default."""

    name: str = "abstract"
    default_model: str = ""

    @abstractmethod
    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        """Return the model's JSON answer. Raise LLMTransportError / LLMOutputError."""

    def is_configured(self) -> bool:
        return True

    def estimate_cost(self, model: str, usage: Usage) -> Decimal | None:
        """USD cost for `usage` on `model`, or None when unknown."""
        return None
