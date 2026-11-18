"""Generate → clarify → save: the NL builder service and its draft record.

`generate` runs one governed LLM call, compiles, validates and files a draft. `answer`
replays the conversation (description, previous extraction, the trader's answers) for an
updated extraction; fields the model changed that no answer addressed are reverted and
reported. The record keeps the whole thread and every ai_call id for traceability.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from ai.llm import (
    AiCallLogger,
    DailyTokenBudget,
    LLMMessage,
    LLMNotConfiguredError,
    LLMOutputError,
    LLMProvider,
    TokenBudget,
    call_structured,
)
from ai.nl_builder.compile import CompileResult, compile_extraction
from ai.nl_builder.extraction import (
    FIELD_GROUPS,
    ClarificationQuestion,
    Language,
    NLCondition,
    NLConditionSet,
    NLExtraction,
    NLLevel,
    NLOperand,
    NLSizing,
)
from ai.prompts import Prompt, load_prompt
from core.time import utcnow
from strategy.dsl import StrategyDocument, validate_document

AGENT = "translator"
TOKENS_PER_CALL = 24_000
MAX_OUTPUT_TOKENS = 4_000
DraftStatus = Literal["draft", "saved", "discarded"]
InstrumentResolver = Callable[[str, str], Awaitable[list[str]]]  # (market, symbol) -> ids


class UnknownQuestionError(ValueError):
    pass


# --- request / response -------------------------------------------------------------------


class GenerateRequest(BaseModel):
    language: Language | None = Field(default=None, description="Hint; detection still runs")
    market: str = Field(default="NSE", min_length=2, max_length=16)
    instrument: str = Field(min_length=1, max_length=32)
    timeframe: Literal["1m", "3m", "5m", "15m", "30m", "1h", "1d", "1w"]
    description: str = Field(min_length=10, max_length=4000)


class AnswerItem(BaseModel):
    question_id: str = Field(pattern=r"^q[0-9]{1,3}$")
    answer: str = Field(min_length=1, max_length=2000)


class AnswerRequest(BaseModel):
    answers: list[AnswerItem] = Field(min_length=1, max_length=20)


class ConditionView(BaseModel):
    original_phrase: str
    rule: str  # deterministic English rendering, e.g. "EMA(9) crosses above EMA(21)"


class RiskView(BaseModel):
    stop_loss: str | None
    target: str | None
    position_sizing: str | None


class ValidationView(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class ThreadMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    ts: datetime


class DraftRecord(BaseModel):
    """Persisted state of one NL draft (table strategy_nl_drafts)."""

    draft_id: str
    user_id: int
    status: DraftStatus = "draft"
    request: GenerateRequest
    extraction: dict[str, Any]
    dsl: dict[str, Any]
    validation: ValidationView
    missing_information: list[str]
    questions: list[ClarificationQuestion]
    defaults_applied: list[str]
    unsupported: list[str]
    changes: list[str] = Field(default_factory=list)  # from the last answer round
    thread: list[ThreadMessage]
    ai_call_ids: list[int]
    strategy_version_id: int | None = None
    created_at: datetime
    updated_at: datetime


class DraftResponse(BaseModel):
    """Wire shape (API spec §8.1 plus validation / defaults / changes / thread)."""

    draft_id: str
    status: DraftStatus
    strategy_name: str
    market: str
    instrument: str
    timeframe: str
    detected_language: Language
    direction: str
    entry_conditions: list[ConditionView]
    exit_conditions: list[ConditionView]
    risk_management: RiskView
    missing_information: list[str]
    clarification_questions: list[ClarificationQuestion]
    unsupported: list[str]
    defaults_applied: list[str]
    validation: ValidationView
    changes: list[str]
    dsl: dict[str, Any]
    original_text: str
    ai_call_id: int | None
    ai_call_ids: list[int]
    thread: list[ThreadMessage]
    strategy_version_id: int | None
    created_at: datetime
    updated_at: datetime


class DraftRepo(Protocol):
    async def create(self, rec: DraftRecord) -> None: ...
    async def get(self, draft_id: str, user_id: int) -> DraftRecord | None: ...
    async def save(self, rec: DraftRecord) -> None: ...


class MemoryDraftRepo:
    def __init__(self) -> None:
        self.rows: dict[str, DraftRecord] = {}

    async def create(self, rec: DraftRecord) -> None:
        self.rows[rec.draft_id] = rec

    async def get(self, draft_id: str, user_id: int) -> DraftRecord | None:
        rec = self.rows.get(draft_id)
        return rec if rec is not None and rec.user_id == user_id else None

    async def save(self, rec: DraftRecord) -> None:
        self.rows[rec.draft_id] = rec


# --- rendering ------------------------------------------------------------------------------

_CMP_WORDS = {
    "crosses_above": "crosses above",
    "crosses_below": "crosses below",
    "greater_than": ">",
    "greater_or_equal": ">=",
    "less_than": "<",
    "less_or_equal": "<=",
    "equals": "=",
}


def render_operand(op: NLOperand) -> str:
    if op.kind == "number":
        v = op.number
        return str(int(v)) if v is not None and v == int(v) else str(v)
    if op.kind == "price":
        return str(op.price)
    assert op.indicator is not None
    ind = op.indicator
    args = [str(ind.period)] if ind.period is not None else []
    args += [f"{k}={v}" for k, v in ind.params.items()]
    s = f"{ind.type}({', '.join(args)})"
    if ind.output:
        s += f".{ind.output}"
    if ind.source != "close":
        s += f"[{ind.source}]"
    if ind.timeframe:
        s += f"@{ind.timeframe}"
    return s


def render_condition(c: NLCondition) -> str:
    left = render_operand(c.left)
    if c.comparison == "between":
        assert c.low is not None and c.high is not None
        return f"{left} between {render_operand(c.low)} and {render_operand(c.high)}"
    if c.comparison in ("rising", "falling"):
        return f"{left} {c.comparison}" + (f" over {c.bars} bars" if c.bars else "")
    assert c.right is not None
    return f"{left} {_CMP_WORDS[c.comparison]} {render_operand(c.right)}"


def render_set(s: NLConditionSet | None, side: str) -> list[ConditionView]:
    if s is None:
        return []
    prefix = f"[{side}] " if side else ""
    return [
        ConditionView(original_phrase=c.original_phrase, rule=prefix + render_condition(c))
        for c in s.conditions
    ]


def render_level(lv: NLLevel | None) -> str | None:
    if lv is None:
        return None
    if lv.unit == "rr":
        return f"{lv.value}R (risk-reward multiple)"
    if lv.unit == "atr":
        return f"{lv.value} x ATR({lv.atr_period or 'period not stated'})"
    return f"{lv.value} {lv.unit}"


def render_sizing(sz: NLSizing | None) -> str | None:
    if sz is None:
        return None
    unit = {
        "fixed_lots": "lot(s)",
        "fixed_quantity": "quantity",
        "fixed_capital": "capital",
        "risk_percent": "% risk per trade",
    }[sz.method]
    v = int(sz.value) if sz.value == int(sz.value) else sz.value
    return f"{v} {unit}"


def draft_response(rec: DraftRecord) -> DraftResponse:
    ex = NLExtraction.model_validate(rec.extraction)
    return DraftResponse(
        draft_id=rec.draft_id,
        status=rec.status,
        strategy_name=ex.strategy_name,
        market=rec.request.market,
        instrument=rec.request.instrument,
        timeframe=rec.request.timeframe,
        detected_language=ex.detected_language,
        direction=str(rec.dsl.get("direction", "long_only")),
        entry_conditions=render_set(ex.entry_long, "long" if ex.entry_short else "")
        + render_set(ex.entry_short, "short"),
        exit_conditions=render_set(ex.exit_long, "long" if ex.exit_short else "")
        + render_set(ex.exit_short, "short"),
        risk_management=RiskView(
            stop_loss=render_level(ex.stop_loss),
            target=render_level(ex.target),
            position_sizing=render_sizing(ex.position_sizing),
        ),
        missing_information=rec.missing_information,
        clarification_questions=rec.questions,
        unsupported=rec.unsupported,
        defaults_applied=rec.defaults_applied,
        validation=rec.validation,
        changes=rec.changes,
        dsl=rec.dsl,
        original_text=rec.request.description,
        ai_call_id=rec.ai_call_ids[-1] if rec.ai_call_ids else None,
        ai_call_ids=rec.ai_call_ids,
        thread=rec.thread,
        strategy_version_id=rec.strategy_version_id,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


# --- questions for what is missing ------------------------------------------------------------

MISSING_TO_FIELD: dict[str, str] = {
    "Entry condition": "entry_conditions",
    "Exit condition": "exit_conditions",
    "Stop loss": "stop_loss",
    "Target": "target",
    "Position sizing": "position_sizing",
    "Product/square-off": "session",
}

QUESTION_ORDER = [
    "entry_conditions",
    "exit_conditions",
    "stop_loss",
    "target",
    "position_sizing",
    "session",
    "direction",
    "timeframe",
    "instrument",
    "other",
]

# Deterministic fallbacks so every missing item has a question even if the model asked none.
FALLBACK_QUESTIONS: dict[str, dict[str, str]] = {
    "entry_conditions": {
        "en": "When exactly should a trade be entered? Name the indicators and the comparison.",
        "mr": "ट्रेड नक्की कधी घ्यायचा? indicator आणि तुलना (उदा. EMA 9 EMA 21 च्या वर गेल्यावर) सांगा.",
        "hi": "ट्रेड ठीक कब लेना है? indicator और तुलना (जैसे EMA 9 EMA 21 के ऊपर जाने पर) बताइए।",
    },
    "exit_conditions": {
        "en": "When should the position exit? "
        "(e.g. EMA 9 crossing below EMA 21, or only at target/stop)",
        "mr": "Exit कधी करायचा? (उदा. EMA 9 EMA 21 खाली आल्यावर, किंवा फक्त target/stop वर)",
        "hi": "Exit कब करना है? (जैसे EMA 9 EMA 21 के नीचे आने पर, या केवल target/stop पर)",
    },
    "stop_loss": {
        "en": "What is the stop loss? (points, percent, or a multiple of ATR)",
        "mr": "Stop loss किती? (points, टक्के, किंवा ATR च्या किती पट)",
        "hi": "Stop loss कितना? (points, प्रतिशत, या ATR का कितना गुना)",
    },
    "target": {
        "en": "What is the target? (points, percent, ATR multiple, or a risk-reward ratio)",
        "mr": "Target किती? (points, टक्के, ATR पट, किंवा risk-reward गुणोत्तर)",
        "hi": "Target कितना? (points, प्रतिशत, ATR गुना, या risk-reward अनुपात)",
    },
    "position_sizing": {
        "en": "How much per trade? (lots, quantity, capital, or % of capital at risk)",
        "mr": "प्रति trade किती? (lots, quantity, capital, किंवा capital चा किती % risk)",
        "hi": "प्रति trade कितना? (lots, quantity, capital, या capital का कितना % risk)",
    },
    "session": {
        "en": "Intraday or carry forward? "
        "If intraday, at what time should open positions be squared off?",
        "mr": "Intraday की carry forward? Intraday असेल तर positions किती वाजता square off करायच्या?",
        "hi": "Intraday या carry forward? Intraday है तो positions कितने बजे square off करनी हैं?",
    },
}


def _questions(
    model_qs: list[ClarificationQuestion],
    missing: list[str],
    compile_errors: list[str],
    lang: Language,
) -> list[ClarificationQuestion]:
    out: list[ClarificationQuestion] = []
    covered: set[str] = set()
    for q in model_qs:
        out.append(q)
        covered.add(q.field)
    fallbacks: list[ClarificationQuestion] = []
    for m in missing:
        f = MISSING_TO_FIELD.get(m)
        if f and f not in covered:
            fq = FALLBACK_QUESTIONS[f]
            fallbacks.append(
                ClarificationQuestion(
                    id="q0", field=f, question_local=fq.get(lang, fq["en"]), question_en=fq["en"]
                )
            )
            covered.add(f)
    fallbacks.sort(key=lambda q: QUESTION_ORDER.index(q.field))
    out.extend(fallbacks)
    for err in compile_errors:
        out.append(
            ClarificationQuestion(
                id="q0",
                field="other",
                question_local=f"Please clarify: {err}",
                question_en=f"Please clarify: {err}",
            )
        )
    # Renumber so ids are unique and stable within this round.
    return [q.model_copy(update={"id": f"q{i + 1}"}) for i, q in enumerate(out)]


# --- diff -------------------------------------------------------------------------------------


def dsl_changes(old: Any, new: Any, path: str = "") -> list[str]:
    """Human-readable leaf diff of two DSL documents."""
    if isinstance(old, dict) and isinstance(new, dict):
        out: list[str] = []
        for k in sorted(set(old) | set(new)):
            p = f"{path}.{k}" if path else k
            if k not in old:
                out.append(f"{p}: added {json.dumps(new[k], ensure_ascii=False)}")
            elif k not in new:
                out.append(f"{p}: removed")
            else:
                out.extend(dsl_changes(old[k], new[k], p))
        return out
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        out = []
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            out.extend(dsl_changes(a, b, f"{path}[{i}]"))
        return out
    if old != new:
        return [
            f"{path}: {json.dumps(old, ensure_ascii=False)} → {json.dumps(new, ensure_ascii=False)}"
        ]
    return []


# --- service ----------------------------------------------------------------------------------


class NLStrategyBuilder:
    def __init__(
        self,
        provider: LLMProvider | None,
        logger: AiCallLogger | None = None,
        *,
        daily: DailyTokenBudget | None = None,
        prompt: Prompt | None = None,
        instrument_resolver: InstrumentResolver | None = None,
        tokens_per_call: int = TOKENS_PER_CALL,
    ) -> None:
        self.provider = provider
        self.logger = logger
        self.daily = daily
        self.prompt = prompt or load_prompt("nl_builder")
        self.resolve_instruments = instrument_resolver
        self.tokens_per_call = tokens_per_call

    @property
    def available(self) -> bool:
        return self.provider is not None and self.provider.is_configured()

    # --- messages ------------------------------------------------------------------------

    @staticmethod
    def _request_message(req: GenerateRequest) -> str:
        payload = {
            "language_hint": req.language,
            "market": req.market,
            "instrument": req.instrument,
            "timeframe": req.timeframe,
            "description": req.description,
        }
        return (
            "Extract the strategy from this description. Use only what it states.\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _answers_message(items: list[AnswerItem], qs: dict[str, ClarificationQuestion]) -> str:
        lines = [
            f"- {a.question_id} ({qs[a.question_id].field}): "
            f"Q: {qs[a.question_id].question_en} A: {a.answer}"
            for a in items
        ]
        fields = sorted({qs[a.question_id].field for a in items})
        return (
            "The trader answered these clarification questions:\n"
            + "\n".join(lines)
            + "\n\nReturn the complete updated extraction. Change ONLY the fields these "
            f"answers cover ({', '.join(fields)}); copy every other field exactly as before. "
            "Keep the original_phrase values of unchanged conditions identical."
        )

    # --- core ------------------------------------------------------------------------------

    async def _extract(
        self, messages: list[LLMMessage], *, user_id: int, refs: dict[str, Any]
    ) -> tuple[NLExtraction, int | None]:
        if self.provider is None or not self.provider.is_configured():
            raise LLMNotConfiguredError("AI is not configured (OPENAI_API_KEY empty)")
        res = await call_structured(
            self.provider,
            agent=AGENT,
            prompt=self.prompt,
            user_messages=messages,
            output_model=NLExtraction,
            input_refs=refs,
            logger=self.logger,
            budget=TokenBudget(self.tokens_per_call),
            daily=self.daily,
            user_id=user_id,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        return res.require(), res.call_id

    async def _compile(
        self, ex: NLExtraction, req: GenerateRequest
    ) -> tuple[CompileResult, ValidationView, list[str]]:
        ids: list[str] | None = None
        if self.resolve_instruments is not None:
            ids = await self.resolve_instruments(req.market, req.instrument)
        comp = compile_extraction(
            ex,
            market=req.market,
            instrument=req.instrument,
            timeframe=req.timeframe,
            original_text=req.description,
            instrument_ids=ids,
        )
        try:
            doc = StrategyDocument.model_validate(comp.dsl)
        except ValidationError as exc:  # compiler bug or schema drift: surface, never hide
            errs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return comp, ValidationView(valid=False, errors=errs, warnings=comp.warnings), []
        rep = validate_document(doc, "draft")
        view = ValidationView(
            valid=not rep.errors and not comp.errors,
            errors=list(rep.errors) + comp.errors,
            warnings=list(rep.warnings) + comp.warnings,
        )
        return comp, view, list(rep.missing_information)

    async def generate(self, req: GenerateRequest, *, user_id: int) -> DraftRecord:
        now = utcnow()
        user_msg = self._request_message(req)
        ex, call_id = await self._extract(
            [LLMMessage(role="user", content=user_msg)],
            user_id=user_id,
            refs={"instrument": req.instrument, "timeframe": req.timeframe},
        )
        comp, view, missing = await self._compile(ex, req)
        return DraftRecord(
            draft_id=f"nld_{uuid4().hex[:24]}",
            user_id=user_id,
            request=req,
            extraction=ex.model_dump(mode="json"),
            dsl=comp.dsl,
            validation=view,
            missing_information=missing,
            questions=_questions(
                ex.clarification_questions, missing, comp.errors, ex.detected_language
            ),
            defaults_applied=comp.defaults_applied,
            unsupported=ex.unsupported,
            thread=[
                ThreadMessage(role="user", content=user_msg, ts=now),
                ThreadMessage(role="assistant", content=ex.model_dump_json(), ts=utcnow()),
            ],
            ai_call_ids=[call_id] if call_id is not None else [],
            created_at=now,
            updated_at=utcnow(),
        )

    async def answer(self, rec: DraftRecord, body: AnswerRequest) -> DraftRecord:
        if rec.status != "draft":
            raise ValueError(f"draft is {rec.status}; it can no longer be changed")
        qs = {q.id: q for q in rec.questions}
        unknown = [a.question_id for a in body.answers if a.question_id not in qs]
        if unknown:
            raise UnknownQuestionError(f"unknown question id(s): {unknown}")
        answered_fields = {qs[a.question_id].field for a in body.answers}
        prev = NLExtraction.model_validate(rec.extraction)
        answers_msg = self._answers_message(body.answers, qs)

        history = [LLMMessage(role=m.role, content=m.content) for m in rec.thread]
        history.append(LLMMessage(role="user", content=answers_msg))
        ex, call_id = await self._extract(
            history, user_id=rec.user_id, refs={"draft_id": rec.draft_id}
        )

        # Never silently change what the trader did not ask to change.
        reverted: list[str] = []
        allowed = {f for field in answered_fields for f in FIELD_GROUPS.get(field, ())}
        if "other" in answered_fields:
            allowed |= {f for group in FIELD_GROUPS.values() for f in group}
        updates: dict[str, Any] = {}
        for group, fields in FIELD_GROUPS.items():
            for f in fields:
                if f in allowed:
                    continue
                if getattr(ex, f) != getattr(prev, f):
                    updates[f] = getattr(prev, f)
                    reverted.append(group)
        if updates:
            ex = ex.model_copy(update=updates)

        comp, view, missing = await self._compile(ex, rec.request)
        changes = dsl_changes(rec.dsl, comp.dsl)
        for g in sorted(set(reverted)):
            view.warnings.append(
                f"the model also tried to change {g}, which no answer addressed; "
                "your original was kept"
            )
        now = utcnow()
        rec.thread.extend(
            [
                ThreadMessage(role="user", content=answers_msg, ts=now),
                ThreadMessage(role="assistant", content=ex.model_dump_json(), ts=utcnow()),
            ]
        )
        if call_id is not None:
            rec.ai_call_ids.append(call_id)
        rec.extraction = ex.model_dump(mode="json")
        rec.dsl = comp.dsl
        rec.validation = view
        rec.missing_information = missing
        rec.questions = _questions(
            ex.clarification_questions, missing, comp.errors, ex.detected_language
        )
        rec.defaults_applied = comp.defaults_applied
        rec.unsupported = ex.unsupported
        rec.changes = changes
        rec.updated_at = utcnow()
        return rec


__all__ = [
    "AnswerItem",
    "AnswerRequest",
    "DraftRecord",
    "DraftRepo",
    "DraftResponse",
    "GenerateRequest",
    "LLMOutputError",
    "MemoryDraftRepo",
    "NLStrategyBuilder",
    "UnknownQuestionError",
    "draft_response",
    "dsl_changes",
]
