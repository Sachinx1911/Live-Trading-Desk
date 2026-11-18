"""Run the NL builder evaluation set and score it at the DSL level.

    uv run python -m ai.evals.nl_eval --offline            # cases self-check, no model
    uv run python -m ai.evals.nl_eval --threshold 0.85     # real model; exit 1 below threshold
    uv run python -m ai.evals.nl_eval --limit 10 --report out.json

Scoring: for each case the model's extraction and the expected shorthand are both compiled
with `compile_extraction`; the DSL sections entry / exit / stop_loss / target /
position_sizing / direction must be identical and the validator's `missing_information`
must match as a set. `unsupported` is checked as a flag (did the model refuse to substitute).
A case passes only when every field matches.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from ai.evals.shorthand import extraction_from_expect
from ai.llm import LLMError, MemoryAiCallLogger, build_provider
from ai.nl_builder import GenerateRequest, NLStrategyBuilder, compile_extraction
from ai.nl_builder.extraction import Language, NLExtraction
from core.settings import get_settings
from strategy.dsl import StrategyDocument, validate_document

CASES_PATH = Path(__file__).resolve().parent / "nl_cases.jsonl"
FIELDS = (
    "direction",
    "entry",
    "exit",
    "stop_loss",
    "target",
    "position_sizing",
    "missing",
    "unsupported",
)
MIN_CASES = 100


@dataclass(frozen=True)
class Case:
    id: str
    lang: Language
    market: str
    instrument: str
    timeframe: str
    text: str
    expect: dict[str, Any]
    tags: tuple[str, ...] = ()

    def request(self) -> GenerateRequest:
        return GenerateRequest(
            language=self.lang,
            market=self.market,
            instrument=self.instrument,
            timeframe=cast(Any, self.timeframe),
            description=self.text,
        )


@dataclass
class Compiled:
    dsl: dict[str, Any]
    missing: set[str]
    errors: list[str]
    unsupported: bool


@dataclass
class CaseResult:
    id: str
    lang: str
    passed: bool
    mismatches: list[str] = field(default_factory=list)
    model_errors: list[str] = field(default_factory=list)
    error: str | None = None  # transport / schema failure: counts as a fail


@dataclass
class EvalReport:
    cases: int
    passed: int
    accuracy: float
    per_field: dict[str, float]
    per_language: dict[str, float]
    tokens: int
    cost_usd: str | None
    model: str
    prompt_version: str
    results: list[CaseResult]

    def summary(self) -> str:
        lines = [
            f"NL builder eval: {self.passed}/{self.cases} passed ({self.accuracy:.1%}) · "
            f"model {self.model} · prompt {self.prompt_version} · tokens {self.tokens}"
            + (f" · cost ${self.cost_usd}" if self.cost_usd else ""),
            "per field : " + ", ".join(f"{k} {v:.0%}" for k, v in self.per_field.items()),
            "per lang  : " + ", ".join(f"{k} {v:.0%}" for k, v in self.per_language.items()),
        ]
        for r in self.results:
            if not r.passed:
                why = r.error or "; ".join(r.mismatches)
                lines.append(f"  FAIL {r.id}: {why}")
        return "\n".join(lines)


# --- cases ---------------------------------------------------------------------------------


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    cases: list[Case] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{n}: {exc}") from exc
        cases.append(
            Case(
                id=d["id"],
                lang=d["lang"],
                market=d.get("market", "NSE"),
                instrument=d["instrument"],
                timeframe=d["timeframe"],
                text=d["text"],
                expect=d["expect"],
                tags=tuple(d.get("tags", [])),
            )
        )
    ids = [c.id for c in cases]
    dupes = [i for i, k in Counter(ids).items() if k > 1]
    if dupes:
        raise ValueError(f"duplicate case ids: {dupes}")
    return cases


def compile_for(case: Case, ex: NLExtraction) -> Compiled:
    comp = compile_extraction(
        ex,
        market=case.market,
        instrument=case.instrument,
        timeframe=case.timeframe,
        original_text=case.text,
        instrument_ids=["1"],  # evaluation never touches the instrument table
    )
    try:
        doc = StrategyDocument.model_validate(comp.dsl)
    except ValidationError as exc:
        return Compiled(comp.dsl, set(), [str(exc)], bool(ex.unsupported))
    rep = validate_document(doc, "draft")
    return Compiled(
        comp.dsl, set(rep.missing_information), comp.errors + list(rep.errors), bool(ex.unsupported)
    )


def expected_for(case: Case) -> Compiled:
    ex = extraction_from_expect(case.expect, name=f"eval {case.id}", lang=case.lang)
    return compile_for(case, ex)


def compare(expected: Compiled, actual: Compiled) -> list[str]:
    out: list[str] = []
    for key in ("direction", "entry", "exit", "stop_loss", "target", "position_sizing"):
        if expected.dsl.get(key) != actual.dsl.get(key):
            out.append(
                f"{key}: expected {json.dumps(expected.dsl.get(key), ensure_ascii=False)} "
                f"got {json.dumps(actual.dsl.get(key), ensure_ascii=False)}"
            )
    if expected.missing != actual.missing:
        out.append(f"missing: expected {sorted(expected.missing)} got {sorted(actual.missing)}")
    if expected.unsupported != actual.unsupported:
        out.append(f"unsupported: expected {expected.unsupported} got {actual.unsupported}")
    return out


def _field_of(mismatch: str) -> str:
    return mismatch.split(":", 1)[0]


# --- offline self-check --------------------------------------------------------------------


def check_cases(cases: Iterable[Case]) -> list[str]:
    """Every case must compile cleanly and declare the exact `missing` list. Returns problems."""
    problems: list[str] = []
    for c in cases:
        try:
            exp = expected_for(c)
        except Exception as exc:  # report every bad case, not just the first
            problems.append(f"{c.id}: expected rules do not parse/compile: {exc}")
            continue
        if exp.errors:
            problems.append(f"{c.id}: expected rules compile with errors: {exp.errors}")
        declared = set(c.expect.get("missing", []))
        if declared != exp.missing:
            problems.append(
                f"{c.id}: declared missing {sorted(declared)} "
                f"but validator says {sorted(exp.missing)}"
            )
    return problems


# --- online evaluation ---------------------------------------------------------------------


async def evaluate(
    builder: NLStrategyBuilder, cases: list[Case], *, concurrency: int = 4
) -> EvalReport:
    logger = (
        builder.logger if isinstance(builder.logger, MemoryAiCallLogger) else MemoryAiCallLogger()
    )
    builder.logger = logger
    sem = asyncio.Semaphore(concurrency)

    async def run(case: Case) -> CaseResult:
        exp = expected_for(case)
        async with sem:
            try:
                rec = await builder.generate(case.request(), user_id=0)
            except LLMError as exc:
                return CaseResult(case.id, case.lang, False, error=f"{type(exc).__name__}: {exc}")
        act = compile_for(case, NLExtraction.model_validate(rec.extraction))
        mism = compare(exp, act)
        return CaseResult(case.id, case.lang, not mism, mism, act.errors)

    results = await asyncio.gather(*(run(c) for c in cases))
    passed = sum(r.passed for r in results)
    field_fail: Counter[str] = Counter()
    for r in results:
        if r.error:
            field_fail.update(FIELDS)
        else:
            field_fail.update({_field_of(m) for m in r.mismatches})
    n = max(len(results), 1)
    per_field = {f: 1 - field_fail[f] / n for f in FIELDS}
    by_lang: dict[str, list[bool]] = {}
    for r in results:
        by_lang.setdefault(r.lang, []).append(r.passed)
    per_language = {k: sum(v) / len(v) for k, v in sorted(by_lang.items())}
    tokens = sum(e.input_tokens + e.output_tokens for e in logger.entries)
    costs = [e.cost_usd for e in logger.entries]
    cost = (
        str(sum(c for c in costs if c is not None))
        if costs and all(c is not None for c in costs)
        else None
    )
    models = {e.model for e in logger.entries}
    return EvalReport(
        cases=len(results),
        passed=passed,
        accuracy=passed / n,
        per_field=per_field,
        per_language=per_language,
        tokens=tokens,
        cost_usd=cost,
        model=", ".join(sorted(models)) or builder.provider.default_model
        if builder.provider
        else "-",
        prompt_version=f"{builder.prompt.name}@{builder.prompt.version}",
        results=list(results),
    )


def _to_json(report: EvalReport) -> dict[str, Any]:
    d = asdict(report)
    if report.cost_usd is not None:
        d["cost_usd"] = str(Decimal(report.cost_usd))
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--offline", action="store_true", help="only self-check the cases file")
    ap.add_argument(
        "--threshold", type=float, default=0.85, help="minimum pass rate (default 0.85)"
    )
    ap.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    ap.add_argument("--lang", choices=["mr", "hi", "en"], default=None)
    ap.add_argument("--report", type=Path, default=None, help="write the JSON report here")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args(argv)

    cases = load_cases()
    if args.lang:
        cases = [c for c in cases if c.lang == args.lang]
    if args.limit:
        cases = cases[: args.limit]

    problems = check_cases(cases)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    if len(load_cases()) < MIN_CASES:
        print(
            f"evaluation set has {len(load_cases())} cases; roadmap requires >= {MIN_CASES}",
            file=sys.stderr,
        )
        return 2
    print(f"{len(cases)} cases self-check OK")
    if args.offline:
        return 0

    provider = build_provider(get_settings())
    if provider is None:
        print("OPENAI_API_KEY not set: skipping the online evaluation (offline self-check passed)")
        return 0
    builder = NLStrategyBuilder(provider, MemoryAiCallLogger())
    report = asyncio.run(evaluate(builder, cases, concurrency=args.concurrency))
    print(report.summary())
    if args.report:
        args.report.write_text(
            json.dumps(_to_json(report), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"report written to {args.report}")
    if report.accuracy < args.threshold:
        print(
            f"FAIL: accuracy {report.accuracy:.1%} below threshold {args.threshold:.0%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
