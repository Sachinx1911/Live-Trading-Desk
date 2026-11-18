"""NL builder evaluation set (roadmap Phase 5).

`nl_cases.jsonl` holds 100+ Marathi / Hindi / English strategy descriptions with the rules a
correct reading must produce, written in a small shorthand (`ai.evals.shorthand`). The
shorthand compiles through the same `compile_extraction` as real model output, so cases are
compared at the DSL level: "RSI()" and "RSI(14)" are the same rule once the documented
default is applied, and a wrong operator or threshold is not.

Offline (always, in CI): every case parses, compiles without errors and yields exactly the
`missing` list the validator reports. Online (when OPENAI_API_KEY is present): the real model
runs each case and the pass rate must meet the threshold recorded in docs/progress.md.
"""
