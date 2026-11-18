from __future__ import annotations

import pytest

from ai.llm import build_provider, llm_status
from ai.llm.openai import OpenAIProvider
from ai.prompts import PromptError, load_prompt, parse_prompt, prompt_names
from core.settings import Settings


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_nl_builder_prompt_loads_with_version() -> None:
    assert "nl_builder" in prompt_names()
    p = load_prompt("nl_builder")
    assert p.name == "nl_builder" and p.version == "1"
    assert "Never invent" in p.system and "missing_information" in p.system


def test_prompt_front_matter_is_enforced() -> None:
    with pytest.raises(PromptError, match="unknown prompt"):
        load_prompt("does_not_exist")
    with pytest.raises(PromptError, match="front matter"):
        parse_prompt("x", "no front matter here")
    with pytest.raises(PromptError, match="version"):
        parse_prompt("x", "---\nauthor: me\n---\nbody")
    with pytest.raises(PromptError, match="empty"):
        parse_prompt("x", "---\nversion: 2\n---\n   ")
    p = parse_prompt("x", "---\nversion: 2\n---\n\nHello\n")
    assert p.version == "2" and p.system == "Hello"


def test_registry_reports_not_configured_without_key() -> None:
    s = _settings(openai_api_key="")
    assert build_provider(s) is None
    assert llm_status(s) == "not_configured"


def test_registry_builds_openai_from_settings() -> None:
    s = _settings(
        openai_api_key="sk-x", openai_model="gpt-4.1-mini", openai_base_url="https://gw.example/v1/"
    )
    p = build_provider(s)
    assert isinstance(p, OpenAIProvider) and p.default_model == "gpt-4.1-mini"
    assert p.base_url == "https://gw.example/v1"
    assert llm_status(s) == "openai:gpt-4.1-mini"


def test_registry_unknown_provider_is_not_configured() -> None:
    assert build_provider(_settings(llm_provider="anthropic", openai_api_key="sk-x")) is None
