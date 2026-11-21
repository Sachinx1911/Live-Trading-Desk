# AI-Powered Multi-Market Algorithmic Trading Platform

Institutional-style, provider-independent algorithmic trading platform for NSE India
(equity, index, futures, options), built as a long-term product: live data, strategy
creation in Marathi/Hindi/English, reproducible backtesting, realistic paper trading,
user-approved live execution, AI-assisted research and trade review.

**Status:** Phase 2 (Upstox integration + collector) — see [`docs/progress.md`](docs/progress.md).

## Start here

| Document | What it is |
|---|---|
| [`docs/MASTER_PROMPT.md`](docs/MASTER_PROMPT.md) | Original requirements, verbatim |
| [`docs/adr/`](docs/adr/README.md) | Architecture decisions, including deviations from the prompt and why |
| [`docs/architecture/01-system-architecture.md`](docs/architecture/01-system-architecture.md) | Processes, package layering, the single engine, data/order/AI paths |
| [`docs/architecture/02-folder-structure.md`](docs/architecture/02-folder-structure.md) | Monorepo layout and conventions |
| [`docs/architecture/03-database-design.md`](docs/architecture/03-database-design.md) | ER diagrams, tables, enums, hypertables, migration plan |
| [`docs/architecture/04-api-specification.md`](docs/architecture/04-api-specification.md) | REST + WebSocket contract |
| [`docs/architecture/05-strategy-dsl.md`](docs/architecture/05-strategy-dsl.md) | The only executable strategy form |
| [`docs/architecture/06-ui-page-map.md`](docs/architecture/06-ui-page-map.md) | Design system and every route |
| [`docs/architecture/07-roadmap.md`](docs/architecture/07-roadmap.md) | 10 phases, exit criteria, Phase 1 task list |
| [`docs/architecture/08-risks-and-dependencies.md`](docs/architecture/08-risks-and-dependencies.md) | External dependencies, risks, open questions |
| [`docs/mark-1-plan.md`](docs/mark-1-plan.md) | Mark 1 plan: JARVIS, the assistant the product becomes; features, stages, screens, data sources |
| [`docs/trading-rules.md`](docs/trading-rules.md) | The owner's hard trading rules enforced by the risk engine |
| [`docs/tool-server.md`](docs/tool-server.md) | Tool server for the owner's jarvis: run it, tokens, tools with levels/tiers, HTTP and MCP |
| [`CLAUDE.md`](CLAUDE.md) | Rules every contributor (human or AI) follows |

## Principles that do not bend

1. One strategy engine and one execution simulator serve backtest, replay and paper trading.
2. Strategies are a validated DSL. No arbitrary code, from users or from LLMs.
3. LLMs write records (drafts, reviews, reports). They never place orders or change approved strategies.
4. Live orders pass through one function behind five gates, with an idempotency key and a kill switch.
5. Paper and live are isolated in schema, services and UI.
6. Market data always shows its source and freshness. No fabricated numbers, ever.
7. Everything stored in UTC; raw data is append-only; derived data can always be rebuilt.

## Stack

Python 3.12 · FastAPI · Pydantic · arq · SQLAlchemy/Alembic · Polars · PostgreSQL 16 +
TimescaleDB · Redis · MinIO/Parquet · DuckDB · Next.js · React 19 · TypeScript · Tailwind ·
shadcn/ui · Lightweight Charts · OpenAI (behind a provider interface) · Docker Compose · Nginx.

## Local development

```bash
cp .env.example .env            # then set SECRETS_KEY, JWT_SECRET, DEV_OWNER_PASSWORD
docker compose up -d          # TimescaleDB (port 5433), Redis
uv sync                       # Python workspace
uv run alembic -c infra/migrations/alembic.ini upgrade head
make seed-owner               # creates the owner user from DEV_OWNER_* in .env
make api                      # http://localhost:8000/api/docs
make worker                   # arq jobs (session checks, sync, backfill, EOD reports)
make collector                # live feed -> candles / quotes / option chains
make web                      # http://localhost:3000
```

With `DEFAULT_MARKET_DATA_PROVIDER=fake` everything runs on deterministic demo data and the
UI says so on every number. Switch to `upstox` after registering an app and logging in on
`/settings/brokers`.

To skip the login screen while developing, set `DEV_AUTO_LOGIN_EMAIL=owner@example.com` in
`.env` (development only; the API refuses it in production).
