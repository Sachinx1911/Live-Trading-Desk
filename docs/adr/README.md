# Architecture Decision Records

Every non-obvious decision gets a short record here so that six months from now
"why did we do it this way" has an answer. Decisions marked **(deviation)** change
something the master prompt specified; the reason is given each time.

| ID | Decision | Status |
|----|----------|--------|
| [ADR-001](ADR-001-modular-monolith.md) | Modular monolith, not microservices | Accepted |
| [ADR-002](ADR-002-one-engine-three-modes.md) | One strategy engine + one execution simulator for backtest, replay, paper | Accepted |
| [ADR-003](ADR-003-strategy-dsl-first.md) | Strategy DSL (Pydantic/JSON Schema) is the only executable strategy form; no Python editor in v1 **(deviation)** | Accepted |
| [ADR-004](ADR-004-timescale-from-day-one.md) | TimescaleDB from Phase 1, not Phase 8 **(deviation)** | Accepted |
| [ADR-005](ADR-005-background-jobs.md) | arq (Redis) for background jobs; no Celery | Accepted |
| [ADR-006](ADR-006-time-and-timezones.md) | All timestamps UTC in storage; exchange timezone per market for display and sessions | Accepted |
| [ADR-007](ADR-007-live-order-gates.md) | Live order path is a single function behind five mandatory gates | Accepted |
| [ADR-008](ADR-008-paper-live-isolation.md) | Paper and live use separate tables, accounts and services | Accepted |
| [ADR-009](ADR-009-llm-boundaries.md) | LLMs produce structured records only; never place orders, never mutate approved strategies | Accepted |
| [ADR-010](ADR-010-market-data-collection-scope.md) | Collect 1-min candles, options-chain snapshots and VIX from Phase 2; raw tick/depth archive is a config flag, off by default | Accepted |
| [ADR-011](ADR-011-corporate-actions-and-cost-schedules.md) | Add corporate_actions, trading_calendars, cost_schedules tables **(addition)** | Accepted |
| [ADR-012](ADR-012-daily-broker-login.md) | Daily broker token renewal is a first-class user workflow | Accepted |
| [ADR-013](ADR-013-news-sentiment-deferred.md) | News/sentiment module deferred until a licensed source is chosen **(deviation)** | Accepted |
| [ADR-014](ADR-014-single-user-rbac-ready.md) | Single operator in v1; schema and auth are multi-user and RBAC ready | Accepted |
| [ADR-015](ADR-015-monorepo-layout.md) | Single repository: apps/ + packages/ + infra/ + docs/ | Accepted |
| [ADR-016](ADR-016-toolchain.md) | Python 3.12+ with uv; Node 24 with pnpm; Docker Compose for all environments | Accepted |
