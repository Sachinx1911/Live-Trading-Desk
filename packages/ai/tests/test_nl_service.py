"""NL builder service with a scripted provider: generate, questions, answers, diffs, reverts."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests_nl_fixtures import MR_TEXT, marathi_extraction_dict  # type: ignore[import-not-found]

from ai.llm import (
    LLMNotConfiguredError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    MemoryAiCallLogger,
    Usage,
)
from ai.nl_builder import (
    AnswerItem,
    AnswerRequest,
    DraftRecord,
    GenerateRequest,
    MemoryDraftRepo,
    NLStrategyBuilder,
    UnknownQuestionError,
    draft_response,
)
from ai.nl_builder.service import dsl_changes


class ScriptedProvider(LLMProvider):
    name = "scripted"
    default_model = "scripted-1"

    def __init__(self, *outputs: dict[str, Any]) -> None:
        self.outputs = list(outputs)
        self.requests: list[LLMRequest] = []

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        out = self.outputs.pop(0)
        return LLMResponse(
            text=json.dumps(out, ensure_ascii=False),
            model="scripted-1",
            usage=Usage(900, 300),
            latency_ms=5,
            cost_usd=None,
        )


def req() -> GenerateRequest:
    return GenerateRequest(
        language="mr", market="NSE", instrument="NIFTY", timeframe="5m", description=MR_TEXT
    )


def with_exit(ex: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = json.loads(json.dumps(ex))
    out["exit_long"] = {
        "op": "and",
        "conditions": [
            {
                "original_phrase": "EMA 9 EMA 21 खाली आल्यावर",
                "left": {"kind": "indicator", "indicator": {"type": "EMA", "period": 9}},
                "comparison": "crosses_below",
                "right": {"kind": "indicator", "indicator": {"type": "EMA", "period": 21}},
            }
        ],
    }
    out["clarification_questions"] = []
    out.update(extra)
    return out


async def test_generate_matches_the_api_spec_shape() -> None:
    provider = ScriptedProvider(marathi_extraction_dict())
    logger = MemoryAiCallLogger()
    svc = NLStrategyBuilder(provider, logger)
    rec = await svc.generate(req(), user_id=1)
    out = draft_response(rec)

    assert out.draft_id.startswith("nld_") and out.status == "draft"
    assert out.strategy_name == "NIFTY EMA Momentum" and out.detected_language == "mr"
    assert (out.market, out.instrument, out.timeframe, out.direction) == (
        "NSE",
        "NIFTY",
        "5m",
        "long_only",
    )
    assert [c.rule for c in out.entry_conditions] == ["EMA(9) crosses above EMA(21)", "RSI() > 55"]
    assert out.entry_conditions[0].original_phrase == "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर"
    assert out.exit_conditions == []
    assert out.risk_management.model_dump() == {
        "stop_loss": None,
        "target": None,
        "position_sizing": None,
    }
    assert set(out.missing_information) == {
        "Exit condition",
        "Stop loss",
        "Target",
        "Position sizing",
        "Product/square-off",
    }
    # One question per missing item: the model's own for exit, deterministic fallbacks for the rest.
    fields = [q.field for q in out.clarification_questions]
    assert fields == ["exit_conditions", "stop_loss", "target", "position_sizing", "session"]
    assert [q.id for q in out.clarification_questions] == ["q1", "q2", "q3", "q4", "q5"]
    assert out.clarification_questions[0].question_local == "Exit कधी करायचा?"
    assert "Stop loss किती" in out.clarification_questions[1].question_local  # Marathi fallback
    assert out.validation.valid and out.dsl["original_text"] == MR_TEXT
    assert out.ai_call_id == 1 and out.ai_call_ids == [1]
    assert [m.role for m in out.thread] == ["user", "assistant"]
    assert logger.entries[0].agent == "translator" and logger.entries[0].validated
    assert logger.entries[0].prompt_version == "nl_builder@1"
    # The request carried the trader's text verbatim and the system prompt first.
    sent = provider.requests[0]
    assert sent.messages[0].role == "system" and MR_TEXT in sent.messages[1].content
    assert sent.schema_name == "NLExtraction"


async def test_answer_applies_only_what_was_asked_and_reports_changes() -> None:
    first = marathi_extraction_dict()
    # The model answers the exit question but ALSO sneaks RSI 55 -> 60 into the entry.
    second = with_exit(first)
    second["entry_long"]["conditions"][1]["right"]["number"] = 60
    second["stop_loss"] = {"original_phrase": "(invented)", "unit": "points", "value": 20}
    provider = ScriptedProvider(first, second)
    svc = NLStrategyBuilder(provider, MemoryAiCallLogger())
    rec = await svc.generate(req(), user_id=1)
    exit_q = next(q for q in rec.questions if q.field == "exit_conditions")

    rec = await svc.answer(
        rec,
        AnswerRequest(
            answers=[AnswerItem(question_id=exit_q.id, answer="EMA 9 EMA 21 खाली आल्यावर")]
        ),
    )
    out = draft_response(rec)
    assert [c.rule for c in out.exit_conditions] == ["EMA(9) crosses below EMA(21)"]
    # The entry change and the invented stop were reverted, and the user is told.
    assert out.dsl["entry"]["long"]["conditions"][1]["right"] == {"kind": "const", "value": 55}
    assert out.dsl["stop_loss"] is None
    assert any("tried to change entry_conditions" in w for w in out.validation.warnings)
    assert any("tried to change stop_loss" in w for w in out.validation.warnings)
    assert out.changes and all(c.startswith("exit") for c in out.changes)
    assert (
        "Exit condition" not in out.missing_information and "Stop loss" in out.missing_information
    )
    assert out.ai_call_ids == [1, 2] and [m.role for m in out.thread] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    # The second call replayed the thread and named the fields the answers cover.
    sent = provider.requests[1]
    assert [m.role for m in sent.messages] == ["system", "user", "assistant", "user"]
    assert "exit_conditions" in sent.messages[-1].content and "खाली" in sent.messages[-1].content


async def test_answer_rejects_unknown_question_and_non_draft_status() -> None:
    svc = NLStrategyBuilder(ScriptedProvider(marathi_extraction_dict()), MemoryAiCallLogger())
    rec = await svc.generate(req(), user_id=1)
    with pytest.raises(UnknownQuestionError):
        await svc.answer(rec, AnswerRequest(answers=[AnswerItem(question_id="q99", answer="x")]))
    rec.status = "saved"
    with pytest.raises(ValueError, match="saved"):
        await svc.answer(rec, AnswerRequest(answers=[AnswerItem(question_id="q1", answer="x")]))


async def test_not_configured_is_explicit() -> None:
    svc = NLStrategyBuilder(None, MemoryAiCallLogger())
    assert not svc.available
    with pytest.raises(LLMNotConfiguredError):
        await svc.generate(req(), user_id=1)


async def test_instrument_resolver_is_used_for_non_index_symbols() -> None:
    seen: list[tuple[str, str]] = []

    async def resolve(market: str, symbol: str) -> list[str]:
        seen.append((market, symbol))
        return ["77"]

    svc = NLStrategyBuilder(
        ScriptedProvider(marathi_extraction_dict()), None, instrument_resolver=resolve
    )
    r = req().model_copy(update={"instrument": "RELIANCE"})
    rec = await svc.generate(r, user_id=1)
    assert seen == [("NSE", "RELIANCE")]
    assert rec.dsl["universe"] == {"kind": "instrument", "instrument_ids": ["77"]}


async def test_record_roundtrips_through_json_and_memory_repo() -> None:
    svc = NLStrategyBuilder(ScriptedProvider(marathi_extraction_dict()), MemoryAiCallLogger())
    rec = await svc.generate(req(), user_id=7)
    repo = MemoryDraftRepo()
    await repo.create(rec)
    assert await repo.get(rec.draft_id, 7) == rec
    assert await repo.get(rec.draft_id, 8) is None  # another user cannot see it
    again = DraftRecord.model_validate_json(rec.model_dump_json())
    assert again == rec and draft_response(again) == draft_response(rec)


def test_dsl_changes_is_a_readable_leaf_diff() -> None:
    old = {"a": 1, "b": {"c": [1, 2]}, "d": None}
    new = {"a": 2, "b": {"c": [1, 3]}, "d": {"x": 1}, "e": "new"}
    assert dsl_changes(old, new) == [
        "a: 1 → 2",
        "b.c[1]: 2 → 3",
        'd: null → {"x": 1}',
        'e: added "new"',
    ]
    assert dsl_changes(old, old) == []
