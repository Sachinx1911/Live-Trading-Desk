"""Natural-language strategy builder (master prompt §7, roadmap Phase 5).

The LLM never writes DSL. It returns an *extraction*: the indicators, comparisons, levels
and sizing it found in the trader's words, each pinned to the original phrase. A
deterministic compiler turns that into a Strategy DSL draft, the DSL validator decides what
is missing, and every missing item gets a clarification question whether or not the model
asked one. Answers re-run the extraction with the conversation so far; anything the model
changes that no answer covered is reverted and reported, never applied silently.
"""

from ai.nl_builder.compile import CompileResult, compile_extraction
from ai.nl_builder.extraction import ClarificationQuestion, NLExtraction
from ai.nl_builder.service import (
    AnswerItem,
    AnswerRequest,
    DraftRecord,
    DraftRepo,
    DraftResponse,
    GenerateRequest,
    MemoryDraftRepo,
    NLStrategyBuilder,
    UnknownQuestionError,
    draft_response,
)

__all__ = [
    "AnswerItem",
    "AnswerRequest",
    "ClarificationQuestion",
    "CompileResult",
    "DraftRecord",
    "DraftRepo",
    "DraftResponse",
    "GenerateRequest",
    "MemoryDraftRepo",
    "NLExtraction",
    "NLStrategyBuilder",
    "UnknownQuestionError",
    "compile_extraction",
    "draft_response",
]
