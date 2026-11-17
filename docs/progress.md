# Progress

Only items that are implemented **and tested** are ticked. "Designed" means the doc exists,
not that code exists.

## Phase 0 · Architecture (first task from the master prompt)

- [x] Master prompt preserved (`docs/MASTER_PROMPT.md`)
- [x] Architecture decision records ADR-001 … ADR-016
- [x] 01 System architecture
- [x] 02 Folder structure
- [x] 03 Database design
- [x] 04 API specification
- [x] 05 Strategy DSL
- [x] 06 UI page map
- [x] 07 Roadmap
- [x] 08 Risks and dependencies
- [x] Plan reviewed by product owner (2026-11-17)

## Phase 1 · Foundation

Verified 2026-11-17 on macOS with Docker Desktop: `docker compose up -d` (db on 5433, redis),
`alembic upgrade head`, `alembic check` (no drift), 32 pytest tests, ruff/mypy strict/import-linter
clean, API login → refresh rotation → providers, worker heartbeat in Redis, web login → dashboard
showing real provider status with explicit Disconnected/Demo states. Web: lint, typecheck, build pass.

- [x] Repo scaffold: uv workspace, pnpm app, docker compose (TimescaleDB, Redis; MinIO behind `--profile storage`)
- [x] `packages/core`: canonical models (instrument, candle, tick, quote, option chain, signal, order intent, fill, position), enums + order state table, settings, async db session, UTC time utils, NSE calendar, structlog, Fernet secret box, event bus
- [x] ORM models (30 tables) + Alembic migrations 0001–0005 (identity, reference seeds, instruments, strategies with immutability trigger, candles/quotes hypertables)
- [x] `MarketDataProvider` / `BrokerAdapter` interfaces, registry, deterministic fake provider (is_demo)
- [x] FastAPI: health, auth (login / refresh with rotation / logout / me), providers status, request logging, JWT + Argon2
- [x] arq worker skeleton with heartbeat cron
- [x] Next.js shell: design tokens, grouped sidebar (15 items), login, dashboard (provider status from API, no fabricated numbers), stub pages per phase
- [x] CI workflow (ruff, mypy, import-linter, alembic upgrade, pytest, web lint+build)
- [x] `.env.example` documented; `infra/scripts/create_owner_user.py` + `make seed-owner`
- [ ] Audit-log writes on state-changing endpoints (table exists; middleware hook lands with the first mutating endpoints in Phase 2)
- [ ] TOTP second factor (schema ready; UI/API in Phase 10 hardening)

## Phase 2 · Upstox integration + collector

Verified 2026-11-17 locally with the fake provider end to end (collector → candles/quotes/
chain snapshots → REST + WebSocket → web). The Upstox adapter is tested against recorded
fixtures and a protobuf round-trip; a live Upstox session has **not** been exercised yet
(no developer app credentials available at build time).

- [x] `packages/providers/upstox`: OAuth (`UpstoxAuth`), multi-window rate limiter, REST client, instrument master mapping, historical v3 + intraday candles with chunking, full quotes, option chain, v3 WebSocket feed (protobuf, re-authorise + backoff), `bind_mapping` to DB ids
- [x] `packages/market_data`: CandleBuilder (ticks → 1m), Resampler, candle/quote/instrument/chain repos, instrument sync, chunked backfill, gap/duplicate quality report, ProviderManager (single/comparison/failover)
- [x] Broker accounts + daily sessions (`core.services.brokers`): encrypted credentials and tokens, `/brokers` API (account upsert, login-url, OAuth callback with state nonce, status, revoke), audit-log writes, Telegram notifier, 08:15 IST + half-hourly session check job
- [x] `apps/collector`: tracked symbols → live feed → 1m candles (DB) + quote cache/pub-sub (Redis) + option-chain snapshots every 5 min (new `option_chain_snapshots` hypertable, migration 0006) + health key; `COLLECT_RAW_TICKS` Parquet writer (off by default)
- [x] Worker jobs: nightly instrument sync, on-demand backfill, EOD gap report, NSE reference import (holidays, corporate actions, F&O lot-size history)
- [x] API: `/instruments`, `/market/candles|quotes|coverage|option-chain|collector`, `/ws/market`
- [x] Web: `/settings/brokers` (credentials, daily login, status), `/settings/notifications`, top-bar broker chip
- [ ] Web: `/market` watchlist + chart, `/market/option-chain`, `/market/providers`, dashboard live index strip (in progress)
- [ ] Import tool (CSV/Excel/JSON/Parquet → data_import_jobs) — deferred to Phase 4 where it is first needed (bhavcopy → D1 candles helper exists in `providers.nse.importer`)
- [ ] Comparison-mode wiring in the collector (second provider arrives in Phase 7; manager logic is tested now)
- [ ] Live Upstox validation: real OAuth login, instrument file, feed during market hours, five unattended sessions on the VPS (exit criterion) — needs the owner's Upstox developer app

## Phase 3 · Trading foundation

- [ ] not started
