# Project rules for Claude Code

This repository is the AI-powered multi-market algorithmic trading platform described in
`docs/MASTER_PROMPT.md`. Read that file and `docs/adr/README.md` before changing anything.

## Non-negotiable safety rules

1. **No LLM ever places, modifies or cancels an order.** Orders are placed only by the
   deterministic execution layer in `packages/execution`.
2. **Live orders go through exactly one function** (`packages/execution/live/gateway.py`)
   behind five gates: approved strategy version, valid broker session, risk engine pass,
   daily loss limit not breached, kill switch off. Never add a second path.
3. **Paper and live never share tables, accounts or services.** See ADR-008.
4. **Never execute arbitrary code** from an LLM or a user. Strategies are DSL/JSON only (ADR-003).
5. **Never display fabricated market data as real.** Every quote and candle carries a
   `source` and a `freshness` state; the UI must show Live / Delayed / Disconnected / Demo.
6. **Never claim an order filled without broker confirmation.** Order state transitions
   come only from broker callbacks or reconciliation.
7. **Approved strategy versions are immutable.** Any change creates a new version in
   `draft` status.
8. **Broker secrets never reach the frontend or the logs.** Credentials live encrypted in
   the database; `.env` holds only the encryption key and infrastructure URLs.

## Architecture rules

- Provider-specific code lives only in `packages/providers/<name>/`. Everything else speaks
  the canonical models in `packages/core/models/`.
- `packages/strategy` + `packages/execution/simulator` are shared by backtest, replay and
  paper trading. Do not fork the logic (ADR-002).
- All stored timestamps are UTC `timestamptz`. Exchange-local times are derived at the
  edges using the exchange's timezone (ADR-006).
- Long-running work (backtests, optimisation, AI research, imports) runs in `apps/worker`
  via arq jobs, never inside an API request.
- Raw market data tables are append-only. Derived data lives in separate tables and can
  always be rebuilt from raw.
- Every DB change is an Alembic migration in `infra/migrations`. Never edit the schema by hand.
- API contracts are typed: Pydantic on the backend, generated TypeScript on the frontend
  (`pnpm gen:api`). Do not hand-write API types in `apps/web`.

## Working rules

- Inspect before editing. Do not overwrite working code without reading it.
- Each module ships with tests. Backtest, risk and order-state code must have
  property-based tests (hypothesis) for their invariants.
- Mark anything mock/demo clearly in code (`DEMO_` prefix, `is_demo` flags) and in the UI.
- Do not mark a feature complete until it is implemented, tested and documented in
  `docs/progress.md`.
- Document every new environment variable in `.env.example` with a comment.
- Communicate with the product owner in Marathi (Devanagari) when discussing; code,
  comments, commits and docs are in English.

## Toolchain

- Python 3.12+ managed with `uv` (`uv sync`, `uv run pytest`).
- Node 24 with `pnpm` (`pnpm install`, `pnpm dev`).
- `docker compose up` starts Postgres+TimescaleDB, Redis, MinIO.
- Lint/format: `ruff` (Python), `biome` or `eslint`+`prettier` (web) as configured in the repo.
