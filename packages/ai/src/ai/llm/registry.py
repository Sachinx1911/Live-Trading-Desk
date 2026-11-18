"""Build the configured provider from settings. Only the provider is chosen here; what it
may be used for is decided by the agents in `ai.*` and nowhere else."""

from __future__ import annotations

from ai.llm.openai import OpenAIProvider
from ai.llm.provider import LLMProvider
from core.settings import Settings


def build_provider(settings: Settings) -> LLMProvider | None:
    """None when AI is not configured; callers show that state, never a fake answer."""
    if settings.llm_provider == "openai":
        key = settings.openai_api_key.get_secret_value()
        if not key:
            return None
        return OpenAIProvider(key, settings.openai_model, base_url=settings.openai_base_url)
    return None


def llm_status(settings: Settings) -> str:
    """Short status for /health and the UI: `not_configured` or `<provider>:<model>`."""
    provider = build_provider(settings)
    if provider is None:
        return "not_configured"
    return f"{provider.name}:{provider.default_model}"
