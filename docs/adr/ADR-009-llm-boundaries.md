# ADR-009: What LLMs may and may not do

**Status:** Accepted · **Date:** 2026-11-14

## Decision
LLM calls go through `packages/ai/llm/provider.py` (`LLMProvider` interface; OpenAI first).
Every call uses a JSON Schema and is validated with Pydantic. Allowed outputs:

- Strategy DSL drafts (status `draft`) and clarification questions.
- Morning briefs, trade reviews, research reports, improvement hypotheses.
- Candidate strategy versions (status `draft`) with linked evidence ids.
- Audit findings.

Forbidden, enforced by not having the capability: placing orders, changing risk limits,
changing any strategy version that is not `draft`, toggling activation, touching the kill
switch (except the deterministic monitor rules, which are not LLM calls).

Every call is logged in `ai_calls` with model, prompt version, tokens, cost and the ids of
the data it was given. Per-job token budgets are mandatory.

## Consequences
- Multi-agent chat frameworks are not used; agents are scheduled jobs that read and write DB records.
