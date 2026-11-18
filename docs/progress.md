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
- [x] Dev-only auto-login (`DEV_AUTO_LOGIN_EMAIL` → `POST /auth/dev-login`, 404 when off, settings refuse it in production); web shell uses it before falling back to `/login`
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

Verified 2026-11-18 end to end on the fake feed: an always-enter smoke strategy on the
paper account entered at the ask (₹42,997.95, charges ₹26.45), hit its ATR stop one bar
later, exited at the bid, and the round trip landed in paper_trades (net −₹104.75), the
journal and performance_daily; the risk engine refused a NIFTY futures lot on a ₹1 lakh
account (exposure cap) as designed. 192 Python tests; ruff, mypy strict, import-linter,
web lint/typecheck/build clean.

- [x] `packages/strategy`: DSL v1 Pydantic schema + validation + JSON Schema + 3 examples; 15 indicators (Polars); event-driven engine (closed bars only, session rules, stop/target/trailing, cooldown, max trades); regime detector
- [x] `packages/execution`: order state machine + idempotency; Indian cost model (static schedule + cost_schedules rows); simulator (market/limit/stop/stop-limit, partial fills, bid/ask fills, seeded slippage); PositionBook with round-trip detection; live gateway with the five gates; Upstox order client reachable only from the gateway (import-boundary test)
- [x] `packages/risk`: RiskLimits, sizing (risk %, lots, caps, drawdown halving), RiskEngine (13 checks, all reasons collected), KillSwitch (Redis), deterministic monitor rules
- [x] Migration 0007: paper_*/live_* tables, reconciliation_runs, kill_switch_events, risk_limits, journal_entries, portfolio_snapshots, performance_daily
- [x] `apps/trader`: activations × live candles → engine → risk → simulator → DB; warm-up from history; square-off/time rules; daily/weekly loss halt (pauses activations, Telegram); kill-switch flatten; health key
- [x] API: `/strategies` (library, immutable versions, transitions, validate), `/paper/*` (accounts, orders+events, positions, trades, activations), `/risk/limits/paper/{id}` (market-hours edit lock), `/risk/kill-switch`, `/events`
- [x] Web: `/paper` (+orders, positions & trades), `/trading` with kill switch, `/settings/risk`, `/strategies` + version detail/editor, `/reports` journal, `/portfolio`, dashboard tiles
- [ ] Live trading remains disabled (`LIVE_TRADING_ENABLED=false`); live_* tables exist, no live runner until Phase 10
- [ ] Engine stop/target are evaluated on closed bars (not tick-level) — the simulator's resting stop orders will be wired in Phase 4 together with the backtester so both modes behave identically
- [ ] Paper account realism: a ₹1 lakh account cannot carry a NIFTY futures lot; demo ran on the NIFTY index instrument. Options/equity universes and margin modelling arrive with Phase 4/5

## Phase 4 · Backtesting and research

Verified 2026-11-18: a one-year NIFTY backtest (98,000 one-minute bars, demo 1m EMA/RSI
version, fake-provider data) ran through API → arq worker → `packages/backtest` in 3 minutes,
stored 716 trades, metrics, equity/drawdown curves, monthly table and a markdown report; the
results page renders them. The result itself is a loss (fees dominate a 1-unit index "trade"
on random-walk data), which is the honest answer. 221 Python tests; ruff, mypy strict,
import-linter, web lint/typecheck/build clean.

- [x] `packages/backtest`: BacktestConfig (assumptions + hash), HistoricalFeed (strict time order, session-aligned resampling, warm-up, next-bar-open fills), runner reusing the strategy engine, risk engine, simulator and position book from paper trading (ADR-002), metrics (24), optimisation (grid/random, sensitivity, plateau, overfit flags), walk-forward (IS/OOS windows, stitched OOS equity, IS/OOS ratio), comparison, deterministic markdown report; golden, determinism, look-ahead and property tests
- [x] Migration 0008: backtest_jobs/results/trades, optimization_jobs/results, replay_sessions
- [x] Worker jobs: run_backtest_job, run_optimization_job, run_walk_forward_job with Redis progress + cancel
- [x] API: `/backtests` (create, list, status with live progress, cancel, results, trades, report), `/backtests/optimizations` (+ walk-forward), `/replay/sessions` + `/ws/replay/{id}`, `/historical/imports` (CSV/XLSX/JSON/Parquet dry-run + commit)
- [x] Replay engine: server-driven clock, play/pause/step/seek/speed, optional strategy overlay with the same engine/simulator, deterministic rewind
- [x] Import tool with validation report, provenance (`provider=import`, manifest hash), `data_import_jobs`
- [x] Web: `/backtesting` workspace, `/backtesting/[jobId]` results (metrics, equity, drawdown, monthly, trades, report, assumptions), `/backtesting/optimize` (+ results, walk-forward windows), `/strategies/compare`, `/tools` (charges + Greeks calculators)
- [x] ADR-017: stops/targets on closed bars in every mode (paper = backtest parity)
- [x] Fixed: bulk candle inserts over asyncpg's 32k-parameter limit are chunked (a month of 1m data failed before)
- [x] Fixed: collector and trader start on Windows (asyncio proactor loop has no `add_signal_handler`; falls back to `signal.signal`)
- [ ] Web `/replay` page and `/tools` import UI (API exists; UI follows in Phase 5 alongside the strategy workspace)
- [ ] Options backtesting on stored chain snapshots / expired contracts (needs Upstox Plus decision)
- [ ] Paper-vs-backtest cross-check report over a recorded live session (needs a real feed day)
- [ ] Deterministic regime per day persisted for the dashboard tile (detector exists; storage in Phase 6)

## Phase 5 · Strategy intelligence

Started 2026-11-18. The LLM boundary from ADR-009 exists and is tested without network
(respx-recorded OpenAI shapes); no agent uses it yet. With `OPENAI_API_KEY` empty `/health`
reports `llm: not_configured` and nothing pretends otherwise.

- [x] `packages/ai/llm`: `LLMProvider` interface (messages + JSON Schema → raw JSON + usage), OpenAI adapter (Chat Completions `response_format=json_schema`, retries with backoff on 408/429/5xx, refusal/truncation/empty → `LLMOutputError`, static price table → `cost_usd` or `None`, key never logged), `TokenBudget` (per-job hard stop, checked before the call) + `DailyTokenBudget` (Redis counter per UTC day), `call_structured` (budget → provider → Pydantic validation → `ai_calls` entry; invalid output is recorded, not raised), provider registry from settings, versioned prompt loader (`prompt_version = <name>@<version>`)
- [x] Migration 0009: `ai_calls` (append-only, indexed by ts / agent / job) + `strategy_versions.ai_call_id` FK; `AiAgent` enum; `DbAiCallLogger` commits each record in its own session so a failed job cannot erase it
- [x] Settings: `OPENAI_MODEL`, `OPENAI_BASE_URL`; `/health.llm`
- [ ] `payload_uri`: archive prompt + raw response to MinIO (Phase 8 storage layer; column exists)
- [ ] NL strategy builder service (`POST /strategies/generate`, clarification thread, missing-information detection, DSL validation, original-text pinning); prompt `nl_builder@1` is drafted
- [ ] Evaluation set (≥100 mr/hi/en descriptions → expected DSL) and CI accuracy gate
- [ ] Visual builder, scanner, approval workflow, AI candidate generation (Mode A), `/strategies/*`, `/scanner`, `/settings/ai` UI
