"""Evaluation set: shorthand parser, offline case validity, and the scorer on a scripted model."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pytest

from ai.evals.nl_eval import (
    MIN_CASES,
    Case,
    check_cases,
    compare,
    compile_for,
    evaluate,
    expected_for,
    load_cases,
    main,
)
from ai.evals.shorthand import (
    ShorthandError,
    extraction_from_expect,
    parse_condition,
    parse_level,
    parse_operand,
    parse_sizing,
)
from ai.llm import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMTransportError,
    MemoryAiCallLogger,
    Usage,
)
from ai.nl_builder import NLStrategyBuilder

# --- shorthand -----------------------------------------------------------------------------


def test_operands_parse() -> None:
    o = parse_operand("BOLLINGER(20,std=2).upper")
    assert o.kind == "indicator" and o.indicator is not None
    assert o.indicator.type == "BOLLINGER" and o.indicator.period == 20
    assert o.indicator.params == {"std": 2} and o.indicator.output == "upper"
    assert parse_operand("close").price == "close"
    assert parse_operand("55").number == 55
    o = parse_operand("EMA(9)[high]")
    assert o.indicator is not None and o.indicator.source == "high"
    with pytest.raises(ShorthandError):
        parse_operand("EMA 9")


def test_conditions_parse() -> None:
    c = parse_condition("EMA(9) crosses_above EMA(21)")
    assert c.comparison == "crosses_above" and c.right is not None
    c = parse_condition("RSI() between 40 and 60")
    assert c.comparison == "between" and c.low is not None and c.high is not None
    c = parse_condition("ADX() rising 3")
    assert c.comparison == "rising" and c.bars == 3
    assert parse_condition("RSI() >= 55").comparison == "greater_or_equal"
    with pytest.raises(ShorthandError):
        parse_condition("RSI() above 55")


def test_levels_and_sizing_parse() -> None:
    lv = parse_level("1.5 atr(10)")
    assert lv is not None and lv.unit == "atr" and lv.value == 1.5 and lv.atr_period == 10
    assert parse_level("2 rr") is not None and parse_level(None) is None
    sz = parse_sizing("0.5 risk_percent")
    assert sz is not None and sz.method == "risk_percent" and sz.value == 0.5
    with pytest.raises(ShorthandError):
        parse_level("twenty points")


# --- the cases file -------------------------------------------------------------------------


def test_cases_file_meets_the_roadmap_bar() -> None:
    cases = load_cases()
    assert len(cases) >= MIN_CASES
    langs = Counter(c.lang for c in cases)
    assert set(langs) == {"mr", "hi", "en"} and min(langs.values()) >= 30
    tags = Counter(t for c in cases for t in c.tags)
    for must in (
        "master-prompt",
        "unsupported",
        "both",
        "short",
        "complete",
        "no-entry",
        "delivery",
        "carry",
    ):
        assert tags[must] >= 1, must


def test_every_case_compiles_and_declares_its_missing_list() -> None:
    problems = check_cases(load_cases())
    assert problems == [], "\n".join(problems)


def test_master_prompt_case_matches_the_documented_draft() -> None:
    case = next(c for c in load_cases() if c.id == "mr-001")
    exp = expected_for(case)
    assert exp.missing == {
        "Exit condition",
        "Stop loss",
        "Target",
        "Position sizing",
        "Product/square-off",
    }
    assert exp.dsl["entry"]["long"]["conditions"][1]["right"] == {"kind": "const", "value": 55}


# --- scoring ---------------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
    name = "scripted"
    default_model = "scripted-1"

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers  # case text -> extraction dict or Exception

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        text = request.messages[-1].content
        for key, ans in self.answers.items():
            if key in text:
                if isinstance(ans, Exception):
                    raise ans
                return LLMResponse(
                    text=json.dumps(ans, ensure_ascii=False),
                    model="scripted-1",
                    usage=Usage(500, 200),
                    latency_ms=1,
                    cost_usd=None,
                )
        raise AssertionError("no scripted answer for request")


def _perfect(case: Case) -> dict[str, Any]:
    ex = extraction_from_expect(case.expect, name="x", lang=case.lang)
    return ex.model_dump(mode="json")


async def test_scorer_passes_perfect_answers_and_fails_wrong_ones() -> None:
    cases = [c for c in load_cases() if c.id in ("mr-001", "hi-002", "en-014", "en-025")]
    answers = {c.text: _perfect(c) for c in cases}
    # en-014: wrong threshold (RSI < 50 instead of < 45) -> entry mismatch only.
    wrong = _perfect(cases[2])
    wrong["entry_short"]["conditions"][1]["right"]["number"] = 50
    answers[cases[2].text] = wrong
    # en-025: transport failure -> counts as a failed case.
    answers[cases[3].text] = LLMTransportError("openai http 503", status=503, retryable=True)

    builder = NLStrategyBuilder(ScriptedProvider(answers), MemoryAiCallLogger())
    report = await evaluate(builder, cases, concurrency=2)
    assert report.cases == 4 and report.passed == 2 and report.accuracy == 0.5
    by_id = {r.id: r for r in report.results}
    assert by_id["mr-001"].passed and by_id["hi-002"].passed
    assert not by_id["en-014"].passed and by_id["en-014"].mismatches[0].startswith("entry:")
    assert by_id["en-025"].error and "503" in by_id["en-025"].error
    assert report.per_field["entry"] == 0.5 and report.per_field["direction"] == 0.75
    assert report.per_language == {"en": 0.0, "hi": 1.0, "mr": 1.0}
    assert report.tokens == 3 * 700 and report.prompt_version == "nl_builder@1"
    assert "FAIL en-014" in report.summary() and "FAIL en-025" in report.summary()


def test_compare_treats_defaulted_periods_as_equal() -> None:
    case = next(c for c in load_cases() if c.id == "en-001")
    exp = expected_for(case)
    stated = json.loads(json.dumps(case.expect))
    stated["entry_long"] = ["EMA(9) crosses_above EMA(21)", "RSI(14) > 55"]
    act = compile_for(case, extraction_from_expect(stated, name="x", lang="en"))
    assert compare(exp, act) == []
    stated["entry_long"] = ["EMA(9) crosses_above EMA(21)", "RSI(14) > 60"]
    act = compile_for(case, extraction_from_expect(stated, name="x", lang="en"))
    assert len(compare(exp, act)) == 1


def test_compare_flags_unsupported_and_missing() -> None:
    case = next(c for c in load_cases() if c.id == "en-013")
    exp = expected_for(case)
    substituted = json.loads(json.dumps(case.expect))
    substituted["unsupported"] = False
    act = compile_for(case, extraction_from_expect(substituted, name="x", lang="en"))
    assert compare(exp, act) == ["unsupported: expected True got False"]


def test_cli_offline_passes_and_skips_online_without_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    assert main(["--offline"]) == 0
    assert main(["--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "self-check OK" in out and "skipping the online evaluation" in out
