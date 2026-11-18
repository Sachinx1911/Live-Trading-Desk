"""AI package (ADR-009). Everything an LLM does in this platform goes through `ai.llm`:
one provider interface, JSON-Schema-constrained calls validated with Pydantic, a hard
per-job token budget and an append-only `ai_calls` record for every request.

What this package can never do is as important as what it does: it has no access to the
execution layer, risk limits, activations or the kill switch. It writes draft strategy
versions and report records only.
"""
