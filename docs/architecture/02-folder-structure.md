# 02 · Folder Structure

```
trading-platform/
├── CLAUDE.md                      # rules for AI-assisted development
├── README.md
├── pyproject.toml                 # uv workspace root (shared tooling config)
├── uv.lock
├── docker-compose.yml             # db, redis, minio (+ app services for VPS profile)
├── .env.example                   # every env var, documented
├── .github/workflows/ci.yml
│
├── apps/
│   ├── api/                       # FastAPI process
│   │   ├── pyproject.toml
│   │   ├── src/api/
│   │   │   ├── main.py            # app factory, lifespan, routers
│   │   │   ├── deps.py            # auth, db session, current user
│   │   │   ├── routers/           # one file per API group (auth, providers, strategies, ...)
│   │   │   ├── ws/                # /ws/market, /ws/orders, /ws/jobs, /ws/replay
│   │   │   └── schemas/           # request/response models (thin, reuse core models)
│   │   └── tests/
│   ├── worker/                    # arq worker process
│   │   ├── src/worker/
│   │   │   ├── main.py            # WorkerSettings, cron schedule
│   │   │   └── jobs/              # backtest, optimisation, import, ai_*, eod, reconciliation
│   │   └── tests/
│   ├── collector/                 # live feed → candles / snapshots / ticks (Phase 2)
│   │   ├── src/collector/
│   │   └── tests/
│   └── web/                       # Next.js (App Router), TypeScript
│       ├── package.json
│       ├── app/                   # routes: (auth)/, (app)/dashboard, strategies, ...
│       ├── components/
│       │   ├── ui/                # shadcn primitives (generated)
│       │   ├── design/            # tokens, DataStateBadge, ModeTag, Money, Pct
│       │   ├── charts/            # Lightweight Charts wrappers, indicator overlays
│       │   └── domain/            # StrategyCard, OrderTable, PositionTable, ...
│       ├── lib/
│       │   ├── api/               # generated client (openapi-typescript) + fetchers
│       │   ├── ws/                # WebSocket client, Zustand stores
│       │   └── format/            # Indian number formatting, IST time
│       └── tests/
│
├── packages/                      # importable Python packages (uv workspace members)
│   ├── core/
│   │   └── src/core/
│   │       ├── models/            # canonical Pydantic models (instrument, candle, tick, quote,
│   │       │                      #   option_chain, order, fill, position, signal, freshness)
│   │       ├── events.py          # in-process async event bus + Redis pub/sub bridge
│   │       ├── calendar/          # exchanges, sessions, holidays, square-off times
│   │       ├── time.py            # UTC helpers, exchange tz conversion
│   │       ├── settings.py        # pydantic-settings
│   │       ├── db/                # SQLAlchemy engine/session, base, mixins (timestamps, user_id)
│   │       ├── secrets.py         # Fernet encrypt/decrypt
│   │       └── logging.py         # structlog setup
│   ├── providers/
│   │   └── src/providers/
│   │       ├── base.py            # MarketDataProvider, BrokerAdapter interfaces
│   │       ├── fake/              # deterministic demo provider (flagged is_demo)
│   │       ├── upstox/            # auth, rest, ws (protobuf), instruments, mapping, ratelimit
│   │       └── dhan/              # Phase 7
│   ├── market_data/
│   │   └── src/market_data/
│   │       ├── manager.py         # ProviderManager: single / comparison / failover
│   │       ├── candles.py         # CandleBuilder (ticks → 1m), resampler (1m → 5m, ...)
│   │       ├── historical.py      # backfill, imports (csv/xlsx/json/parquet), export
│   │       ├── quality.py         # gaps, duplicates, provider comparison
│   │       ├── options.py         # chain snapshots, greeks
│   │       └── repo/              # DB access for candles/quotes/snapshots
│   ├── strategy/
│   │   └── src/strategy/
│   │       ├── dsl/               # schema.py (Pydantic), validate.py, json_schema export
│   │       ├── indicators/        # one module per indicator, registry, tests vs reference
│   │       ├── engine.py          # MarketEvent → Signal
│   │       ├── regime.py          # regime detector
│   │       └── repo/
│   ├── execution/
│   │   └── src/execution/
│   │       ├── orders.py          # order model + state machine
│   │       ├── simulator/         # fills, slippage, partial fills, cost model
│   │       ├── costs.py           # cost_schedules lookup
│   │       ├── live/
│   │       │   ├── gateway.py     # THE single live-order entry point (5 gates)
│   │       │   └── reconcile.py
│   │       ├── oms.py             # order lifecycle records
│   │       └── repo/
│   ├── risk/
│   │   └── src/risk/
│   │       ├── engine.py          # ALLOW / REJECT with reasons
│   │       ├── sizing.py
│   │       ├── limits.py          # daily/weekly loss, drawdown, exposure, correlation
│   │       ├── kill_switch.py
│   │       └── repo/
│   ├── backtest/
│   │   └── src/backtest/
│   │       ├── runner.py          # event-driven loop (simulated clock)
│   │       ├── metrics.py
│   │       ├── optimise.py        # grid/random, walk-forward, sensitivity
│   │       ├── replay.py          # replay session controls
│   │       └── repo/
│   ├── portfolio/
│   │   └── src/portfolio/
│   │       ├── accounts.py        # paper and live account services (separate classes)
│   │       ├── pnl.py
│   │       ├── analytics.py
│   │       ├── journal.py
│   │       └── repo/
│   └── ai/
│       └── src/ai/
│           ├── llm/               # LLMProvider interface, openai.py, budget, logging
│           ├── prompts/           # versioned prompt files (prompt_version in ai_calls)
│           ├── nl_builder.py      # text → DSL draft + clarifications
│           ├── research.py
│           ├── review.py
│           ├── brief.py
│           ├── auditor.py
│           ├── evals/             # NL builder evaluation set (mr/hi/en → expected DSL)
│           └── repo/
│
├── infra/
│   ├── docker/                    # Dockerfiles (api, worker, collector, web), nginx.conf
│   ├── migrations/                # Alembic env + versions/
│   └── scripts/                   # create_owner_user.py, backup.sh, restore_test.sh
│
└── docs/
    ├── MASTER_PROMPT.md
    ├── adr/
    ├── architecture/
    │   ├── 01-system-architecture.md
    │   ├── 02-folder-structure.md
    │   ├── 03-database-design.md
    │   ├── 04-api-specification.md
    │   ├── 05-strategy-dsl.md
    │   ├── 06-ui-page-map.md
    │   ├── 07-roadmap.md
    │   └── 08-risks-and-dependencies.md
    └── progress.md                # what is actually done and tested, per phase
```

## Conventions

- **One repo, one lockfile per ecosystem.** `uv` workspace for Python, `pnpm` for web.
- **`src/` layout** for every Python package; tests beside the package in `tests/`.
- **`repo/`** folders hold SQLAlchemy queries; domain modules never build SQL inline.
- **Provider-specific code** exists only under `packages/providers/<name>/`. A grep for
  `upstox` outside that folder (and config) should return nothing.
- **Generated code** (`apps/web/lib/api/generated.ts`, `components/ui/*`) is committed but
  never hand-edited.
- **Demo/mock** code carries `fake`/`demo` in its path or name and sets `is_demo=True`.
- **Migrations** are the only way the schema changes; `alembic check` runs in CI.
