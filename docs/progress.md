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
- [x] Login page never shown while dev auto-login is on (owner, 2026-11-21: "login sadhya kadun tak" until the project is finished): API not reachable → "Connecting to the API" with a 3 s retry instead of `/login`; `/login` itself signs in and forwards; an expired session signs in again. The form appears only when the API answers that dev login is off (production). Checked in the browser with the API stopped and restarted
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
- [x] Live Upstox validation (2026-11-18, after the owner's segments were reactivated): OAuth login → session valid until 03:30 IST; instrument master 47,011 rows synced (NIFTY lot 65); REST quotes, option chain (316 rows), v3 WebSocket connected (7 keys, full mode); historical backfill from the real API: NIFTY/BANKNIFTY/RELIANCE/HDFCBANK/VIX daily since 2010, NIFTY/BANKNIFTY 5m and NIFTY 15m since Jan 2022, NIFTY 1m last year (Upstox holds no intraday before 2022). Fixes found on the way: daily bars stamped at 00:00 IST shifted a UTC day (now 09:15 IST open), WebSocket SSL needed certifi on macOS, sub-15-minute requests must not span a calendar month (28-day chunks), inconsistent OHLC (VIX) widened instead of dropped, quote cache TTL raised to a week so the last close survives the session with an honest "stale" badge, collector symbols moved into Settings
- [ ] Five unattended market sessions on the VPS with gap reports (needs the VPS; market-hours feed not yet observed)

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

## Design system · TradingView reference (2026-11-18)

- [x] Reverse-engineered reference recorded in `docs/architecture/09-design-reference-tradingview.md`
- [x] Web restyled to it: #000 panes + #222 chrome + #303030 dividers, #2962ff accent (purple only for AI), system 14px type with tabular numerals, 52px icon rail (expands to 220px), 38px top bar with symbol-search pill, 28px pill buttons/tabs, 34px chips, 50px/41px/34px table rows, glass dialogs, grid-less #000 charts with #089981/#f23645 candles and 45% volume, 360px glass login
- [x] Light theme (TradingView light: #ebebeb page, white panes, #f2f2f2 controls, #222 selected pill) with a Dark / Light / System switch in the user menu and `/settings/profile`; applied before first paint, charts re-skin live
- [ ] Hover/transition tokens still measured by eye, not from TradingView

## Design system · HUD theme (2026-11-21, owner request "old design change kar")

- [x] Dark theme replaced by the HUD palette from `references/design-reference-images.md`: navy `#05080f` page, `#0a1220` panels, cyan `#5fd4ff` line/accent, ice-blue text, amber `#ffb347` for panel headers and warnings, red `#ff4d4d` only for danger, green only for positive P&L; near-square radii; faint grid and top glow behind panels
- [x] New utilities `hud-label` (mono, uppercase, 0.12em), `hud-frame` (bracketed corners), `hud-glow`; `.hud-panel` unfold animation 0.22 s, off with reduced motion
- [x] `PanelCard` (every panel), sidebar (cyan active edge, mono group labels), top bar (ring badge, mono page title, outlined status pills), login badge; chart palette fallback updated (charts read the tokens)
- [x] Light theme kept as the daytime option (TradingView light, square HUD radii reverted there); Dark / Light / System switch unchanged
- [x] Index tiles: HUD frame, monospaced symbol label, 36px tabular hero price; demo quotes keep the demo stripes instead of the frame (the demo marking wins)
- [x] `tsc --noEmit` and eslint clean; login, dashboard and market pages checked in the browser (no market data running, so prices showed as Disconnected)
- [ ] Remaining pages checked one by one; P&L and PCR hero numbers; look of live prices and demo stripes with the collector running; JARVIS core, ring and tile-grid components come with Stage 4 panels

## Market regime · Module 6 (2026-11-18, deterministic, no LLM)

- [x] `strategy/regime.py`: daily regime (trend up/down/sideways from close·EMA20·EMA50 with ADX confirmation, strength from ADX, volatility from the VIX 1-year percentile or ATR %, structure from swing highs/lows, event flag) and intraday day type after 09:45 IST (opening range, VWAP distance, ATR ratio)
- [x] Migration 0011: `regime_daily`, `regime_intraday`, `backtest_results.regime_table`, `backtest_trades.regime`
- [x] Worker jobs: daily at 09:05 and 16:10 IST, intraday every 15 min in session; `POST /market/regime/recompute`
- [x] API `/market/regime` + `/market/regime/summary`; trader passes the regime to the strategy engine's `regime_filters` and tags every closed paper trade; backtests tag trades and produce a "By regime" table in results and the markdown report
- [x] Web: dashboard regime tile, `/market` regime strip with 30-day history cells, regime pills in paper/backtest trade tables, "By regime" panel on backtest results
- [x] First real run (Upstox daily data): NIFTY 2026-11-17 up/strong, vol normal (VIX 15.5 = 68th percentile), ADX 41; BANKNIFTY up/strong
- [ ] Breadth (stocks above 50-DMA) needs the full NIFTY 50 universe — Phase 9 data scope
- [ ] Intraday day type not yet observed live (first market session pending)

## Phase 5 · Strategy intelligence

Started 2026-11-18. The LLM boundary from ADR-009 exists and is tested without network
(respx-recorded OpenAI shapes); no agent uses it yet. With `OPENAI_API_KEY` empty `/health`
reports `llm: not_configured` and nothing pretends otherwise.

- [x] `packages/ai/llm`: `LLMProvider` interface (messages + JSON Schema → raw JSON + usage), OpenAI adapter (Chat Completions `response_format=json_schema`, retries with backoff on 408/429/5xx, refusal/truncation/empty → `LLMOutputError`, static price table → `cost_usd` or `None`, key never logged), `TokenBudget` (per-job hard stop, checked before the call) + `DailyTokenBudget` (Redis counter per UTC day), `call_structured` (budget → provider → Pydantic validation → `ai_calls` entry; invalid output is recorded, not raised), provider registry from settings, versioned prompt loader (`prompt_version = <name>@<version>`)
- [x] Migration 0009: `ai_calls` (append-only, indexed by ts / agent / job) + `strategy_versions.ai_call_id` FK; `AiAgent` enum; `DbAiCallLogger` commits each record in its own session so a failed job cannot erase it
- [x] Settings: `OPENAI_MODEL`, `OPENAI_BASE_URL`; `/health.llm`
- [ ] `payload_uri`: archive prompt + raw response to MinIO (Phase 8 storage layer; column exists)
- [x] NL strategy builder (`packages/ai/nl_builder`): the model returns an *extraction* (indicators, comparisons, levels, sizing, each pinned to the trader's `original_phrase`), never DSL; a deterministic compiler builds the DSL draft (same extraction → same DSL), `validate_document(target="draft")` decides `missing_information`, and every missing item gets a clarification question (model's own or a mr/hi/en fallback). Structural defaults the DSL needs (session product, index → current-month future, RSI/ATR/ADX period) are applied *and listed* in `defaults_applied`. Answers replay the thread; model changes to fields no answer covered are reverted and reported as warnings; the DSL diff is returned as `changes`
- [x] API: `POST /strategies/generate`, `GET/POST .../{draft_id}`, `.../answer`, `.../save` (creates strategy + DRAFT version through the editor's path, links `ai_call_id`); 503 `ai_not_configured`, 429 `ai_budget_exceeded`, 502 `ai_invalid_output`/`ai_upstream_error`; audit rows for generate/answer/save
- [x] Migration 0010: `strategy_nl_drafts` (request, extraction, dsl, validation, questions, thread, ai_call_ids, strategy_version_id)
- [x] Web `/strategies/new/natural-language`: form (language, market, instrument, timeframe, description), extracted rules with original phrases, risk summary, defaults applied, validation, clarification questions → answers, DSL viewer, save → strategy page; honest "AI not configured" state
- [ ] Live run against OpenAI (needs `OPENAI_API_KEY`): first `nl_eval` measurement, record accuracy per language here and tune `nl_builder` (bump to `@2` on any prompt change)
- [x] Evaluation set: 108 cases (36 mr / 36 hi / 36 en) in `packages/ai/src/ai/evals/nl_cases.jsonl`, expected rules in a small shorthand (`ai.evals.shorthand`) that compiles through the same `compile_extraction` as model output, so scoring is at the DSL level (entry / exit / stop_loss / target / position_sizing / direction identical, `missing_information` equal as a set, `unsupported` flag). Offline self-check (every case compiles cleanly and declares the exact `missing` list) runs in CI always; the model run `uv run python -m ai.evals.nl_eval` is gated on `OPENAI_API_KEY` and fails CI below the threshold. **Threshold: 0.85 pass rate** (prompt `nl_builder@1`); first measured run pending the key. Report JSON uploaded as a CI artifact
- [x] DSL catalogue for builders: `GET /strategies/dsl/catalogue` (indicators from the engine registry with param defaults and outputs, every DSL enum from the Pydantic Literals, order/stop types, regime values) and `GET /strategies/dsl/schema` (JSON Schema); the web falls back to a bundled copy of the catalogue when the API is unreachable and says so
- [x] Visual strategy builder `/strategies/new/visual` (no code, forms → DSL v1): basics, universe (index / future of underlying / options with expiry and strike rules / equity list), session (product, windows, weekdays, time and regime filters), indicators from the catalogue with context timeframes, nested AND/OR condition tree with crossover / compare / threshold / bar-pattern rules for entry and exit (long and short), confirmation / cooldown / time exit, stop, targets with partials, trailing, sizing and order types. Client-side checks per section, "Validate on server" (same validator as the editor), "Save as new strategy" through `POST /strategies`; draft autosaved in localStorage; examples loadable; DSL shown as a tree or raw JSON. Strategy page gained "Edit visually" (loads an existing version) and saves a new DRAFT version. Verified end to end: example → validate → save → `/strategies/3` (origin `user_visual`)
- [x] Market scanner (Module 23, deterministic): migration 0012 `scan_snapshots` (per instrument per day: price/volume metrics, returns 1/5/20 d, 52-week position, ATR %, RSI, EMA stack, distance from 20/50/200 DMA, volume ratio, gap %, regime, OI change for F&O) + `scan_presets` (14 seeded: gainers/losers, breakouts, volume spikes, oversold/overbought, trend-up above DMAs, gap ups/downs, high ATR, near 52-week high/low, VIX context…). Filter engine (`market_data/scanner/filters.py`) evaluates typed conditions over the snapshot with AND/OR; `POST /scanner/run`, `GET /scanner/presets`, `GET /scanner/snapshot/latest`, `POST /scanner/snapshot/rebuild`; nightly rebuild job 16:20 IST after the EOD gap fill
- [x] Universe: NIFTY 50 constituents' daily candles backfilled from Upstox (52 symbols since 2010, TATAMOTORS no longer listed under that symbol); regime computed for all 55 instruments; snapshot 2026-11-18 has 55 rows; sample "top equity gainers" scan verified through the API
- [x] Web `/scanner`: preset rail, filter builder (metric / operator / value rows, AND/OR), sortable result table with sparkline-free numeric columns, snapshot date + "as of" freshness, link into `/market` for a row
- [x] Approval workflow (user acts only, ADR-009): `GET /strategies/versions/{id}/readiness` (succeeded backtests of that exact version with return / drawdown / PF, paper and live activations, allowed transitions and the reason for every blocked one) and `GET .../approvals` (log with user, from → to, decision, note, evidence). Transition gates on the server: `backtested` needs ≥1 succeeded backtest of the version, `approved_live` needs a paper run and the owner role, reject / retire / approve-live need a note; evidence (backtest job ids, paper runs) is attached automatically. Web: pipeline strip draft → backtested → validated → paper → approved live, evidence tables, one button per allowed transition (blocked ones explain why), LIVE approval needs the word LIVE typed, approval log under the version. Verified: strategy 1 v3 draft → backtested with note and evidence `#3, #2`
- [x] Web `/replay`: setup (instrument, date defaulting to the last weekday, 1m–1h view timeframe, optional strategy version, speed 1×–300×), streaming chart (dimmed stored context bars before the day, replay bars appended as they arrive, fill markers, volume), transport bar (play / pause / step 1-5-20 / step back / speed / seek slider / cursor time IST / status), tabs for events (signals, risk rejections with reasons, orders, fills), positions, trades and equity, open-session list (resume / delete), session deleted on End or page leave. Honest states: not a trading day, no 1-minute candles (links to coverage), demo bars flagged. Fix found while building it: replay loaded candles from every provider (375 Upstox + 41 fake bars for NIFTY 2026-11-17); the replay router now uses the active provider only, like `/market/candles`
- [x] Web `/tools` historical import: drop or pick CSV / Parquet / Excel / JSON (≤50 MB), CSV header read client-side to auto-map columns, mapping form (exchange, timeframe, symbol or symbol column, timestamp column + format, timezone, OHLC / volume / OI), dry run report (read / accepted / rejected, coverage per symbol, rejections with reasons and samples, warnings, content hash), commit only after a clean dry run of the same file + mapping (≤5 % rejected, owner role, inline confirm), jobs table. Everything imported is provider `import` and labelled so
- [x] Web `/settings/ai`: LLM status from `/health` (not configured / provider:model), where the key lives (server `.env` only, no input field by design), the ADR-009 boundary, Phase 6 list; "AI" card on the settings index
- [x] Web API client surfaces FastAPI `detail` messages in `ApiRequestError`
- [ ] `pnpm gen:api` regeneration (hand-appended sections in `lib/api/generated.ts` for scanner, approval, replay and imports should be replaced by the generated contract once the openapi-typescript pipeline runs in CI)
- [ ] AI candidate generation (Mode A) and the research agents — last, when the OpenAI key is supplied

## Owner trading rules (2026-11-21)

Registry of the owner's hard market rules in `risk/owner_rules.py`, run by the risk engine on every entry; documented in `docs/trading-rules.md`. More rules will be added here.

- [x] Rule 1 `pcr_guard`: PCR ≥ 2 → no PUT buy, PCR ≤ 0.5 → no CALL buy. PCR from the nearest-expiry chain snapshot (`market_data/repo/chains.py: latest_chain_oi`); the trader passes it as `MarketContext`; missing or >15 min old chain blocks option buys; backtest/replay record `pcr_guard:skipped`. Unit + property tests
- [ ] Not yet verified on a live session (database was down when it was built); show PCR on the `/market` option chain and in the rejection journal UI
- [ ] Chain history in backtest/replay so the rule is enforced there too

## Option-chain cadence (2026-11-21)

- [x] Chain snapshot interval is a setting, `COLLECT_CHAIN_INTERVAL_S`, default 180 s (was a fixed 5 minutes); ADR-010 updated
- [x] `uv run python -m collector.oi_cadence --underlying NIFTY --minutes 20 --poll 15`: read-only tool that polls the chain and reports how often OI really changes
- [ ] Run the cadence tool in a live session and record the measured gap here (built on a Saturday; Sensibull states about 3 minutes)


## Mark 1 Stage 1.1 · Per-strike option series (2026-11-21, `docs/mark-1-build-plan.md` §1.1)

- [x] Migration 0013 `option_strike_series` (hypertable on `ts`, compressed after 30 days): one row per strike and side of every stored chain snapshot with OI, OI change from the day's open, LTP, volume, IV, delta, gamma, theta, vega; derived and rebuildable from `option_chain_snapshots`
- [x] `market_data.strike_series`: pure `derive_points` / `opening_oi`; opening baseline = first non-empty snapshot at or after 09:15 IST of the same day, underlying, expiry and provider; before that or without a baseline the change is null, never guessed
- [x] Collector writes the derived rows right after each raw snapshot, inside a savepoint so a derivation error never loses the raw snapshot
- [x] Worker job `rebuild_strike_series_job(symbol, day)` replaces one IST day from raw
- [x] Tests: derivation, bad rows, 09:15 IST boundary; hypothesis properties (per-side OI totals equal `oi_totals`, change against itself is zero); DB test that live writes equal a rebuild; collector, worker and core suites green; ruff, mypy, import contracts clean
- [ ] Check with real Upstox chains during market hours (strike decimals, missing Greeks)

## Mark 1 Stage 1.2 · OI Change chart (2026-11-21, `docs/mark-1-build-plan.md` §1.2)

- [x] `market_data.oi_change`: `compare_chains` (per-strike call/put OI at both ends over the union of strikes; no change claimed when a side is missing at one end), `pcr`, `snapshot_pair` (first stored snapshot at or after the start, last at or before the end, one provider, expiry matched by IST date), `expiries_on_day`
- [x] API `GET /market/oi-change?underlying_id&expiry&day&start&end` (IST HH:MM, default 09:15–15:30, end capped at now) → strikes, totals, PCR and spot at both ends, snapshot times used, source, freshness (demo / delayed / stale / historical); 404 when the window holds no snapshot; `GET /market/oi-change/expiries?underlying_id&day`
- [x] Web `/market/oi-change` (nav "OI Change"): NIFTY/BANKNIFTY, day, expiry, from/to with presets (full day, last 15/30/60 min), ATM ± 5/10/15/all strikes; hero stats (call Δ, put Δ, PCR, spot with start values); SVG bars per strike, calls cyan and puts amber, ATM shaded; snapshot times used vs asked; DEMO banner and freshness badge; honest empty states
- [x] Sidebar marks only the most specific matching item active
- [x] Fake provider (DEMO): chain OI now drifts through the day, deterministic per strike, so OI-change views show movement in demo mode
- [x] Tests: comparison and PCR, hypothesis properties (change = to − from, a chain against itself never changes), DB test for the snapshot choice and expiries; ruff, mypy, tsc, eslint clean; checked in the browser with demo data
- [ ] Check with real Upstox chains during market hours

## Mark 1 Stage 1.3 · Greeks view (2026-11-21, `docs/mark-1-build-plan.md` §1.3)

- [x] Option chain table: "Greeks" toggle adds gamma, theta (per day) and vega next to IV and delta on both sides; values exactly as the provider sent them, "—" when missing; column tooltips; ATM row highlighted; CALLS/PUTS headers in cyan/amber (red stays for danger)
- [x] Fake provider (DEMO): gamma, theta and vega from Black-Scholes with zero rate, so the demo chain fills every column; fake provider test asserts their signs
- [x] tsc, eslint, ruff, mypy clean; checked in the browser with demo data
- [x] "At" date + time picker on the option chain page: `GET /market/option-chain?at=` returns the last snapshot stored at or before that moment (freshness historical), "Back to latest" returns to live; checked in the browser
- [ ] Check with real Upstox chains (which Greeks Upstox sends, units of theta and vega)

## Mark 1 Stage 2 · Owner rules on stored chain history (2026-11-21, `docs/mark-1-build-plan.md` §2)

- [x] `risk.market_history.PcrHistory`: sorted PCR points of an underlying; `context_at(now)` gives the owner-rule `MarketContext` from the newest point at or before `now` (never later); before the first point the PCR is missing, so the rule blocks like in paper
- [x] `market_data.repo.chains.chain_oi_history` (put/call OI totals per stored snapshot, summed in SQL with the `oi_totals` rule, nearest unexpired expiry, one provider) and `underlying_chain_oi_history` (for an option contract's underlying, one day of lead-in)
- [x] Backtest: `run_backtest(..., market_history=)`; the worker's backtest job loads the history from the candles' provider; `pcr_guard` now blocks in backtests exactly as in paper; result assumptions record `owner_rules_market_data` (points and range, or "none: rules ... skipped")
- [x] Replay: sessions on an option load the day's history; the overlay's risk check gets the context per bar
- [x] Tests: `PcrHistory` unit + hypothesis no-look-ahead property; SQL totals equal `oi_totals` and nearest expiry / provider filter (DB); backtest on a PUT blocked at PCR 2.5, allowed at 1.0, skipped without history; replay blocks a PUT buy with high-PCR history; risk, backtest, market_data, execution, strategy, api, worker, trader suites green
- [x] Optimisation, walk-forward and compare runs get the same stored chain history (`market_history`, `option_history`) as a single backtest, so `pcr_guard` and option features behave identically there (test: high-PCR history blocks put buys in every optimisation run and in a comparison)
- [x] DSL 1.1 `option` operand (`pcr`, `iv_atm`, strike `oi`, `oi_change_from_open`, `greek` at ATM ± 10 strikes): schema + `v1.1.json` (1.0 documents stay valid), validator (refuses the operand in 1.0, warns about chain history), `strategy.option_features` (`ChainView`, `ChainHistory` with opening baseline, no look-ahead), engine `option_provider`
- [x] Fed everywhere from stored snapshots of the underlying: backtest (`option_history`, loaded only when the strategy uses options; assumptions record the snapshot count), replay, paper trader (`trader.live_chain.LiveChain`, refreshed before each bar); `market_data.repo.chains.chain_snapshots_between` / `chain_underlying_id`
- [x] Visual builder: "Option chain" operand (feature, ATM offset, CE/PE, Greek); builder saves DSL 1.1; API catalogue lists the operand; DSL doc §3.2 and §12 updated
- [x] Tests: schema rules, values, opening baseline, hypothesis no-look-ahead, validator, backtest entries on `pcr < 1` (trades at 0.5, none at 2.0 or without data); full strategy, backtest, risk, ai (NL self-check 108 OK), market_data, api, worker, trader suites green; builder checked in the browser
- [ ] NL builder: extraction does not yet produce `option` operands ("PCR 1 च्या खाली असेल तर" stays unsupported)
- [ ] The owner's next trading rules

## Mark 1 Stage 3.5 · Raw news ingest (2026-11-21, `docs/mark-1-build-plan.md` §3.5, no AI)

- [x] `market_data/news`: feed list from `NEWS_FEEDS` (defaults checked with a real GET on 2026-11-21: Economic Times Markets, LiveMint Markets). Moneycontrol Markets and Business (AI-MIOS) answer 200 but are frozen at 2024-04-23, so they are not defaults; any feed whose newest item is older than 7 days is reported as `stale feed` in `ingest_errors`
- [x] RSS/Atom parsing with `feedparser` (document bytes only); title, link (tracking params and fragment stripped), feed summary (tags removed, 1000 chars) and published time in UTC; never article bodies, never page scraping
- [x] Ingest: one GET per feed per run, sequential, named User-Agent, timeout (`NEWS_FETCH_TIMEOUT_S`), 5 MB cap, no retries; `ON CONFLICT (url) DO NOTHING`; each feed committed separately; failures to `ingest_errors`; per-feed last result in Redis `news:feeds`
- [x] Symbol tagging without AI (`market_data/news/tagger.py`): symbol token + curated NIFTY 50 / index aliases + name-derived alias, group-company exclusions (Reliance Power, SBI Life, Nifty Bank…); computed at query time over NSE equities/indices with daily candles from the active provider (no migration)
- [x] Worker `ingest_news` every 30 min 07:00–22:30 IST; API `GET /news` (since, source, q, symbol, limit), `GET /news/sources`, `POST /news/ingest` (owner, enqueues)
- [x] Web `/news` (filters by source / symbol / search, IST times, link out, honest empty state, failing/stale feed notice, owner "fetch now"), "News" panel for the selected stock/index on `/market`, nav entry
- [x] Verified live: 85 headlines (ET Markets 50, LiveMint 35); re-run added 0 (dedup); 29 of 85 tagged
- [ ] News analysis (sentiment, materiality) waits for Stage 4 (OpenAI key)

## Mark 1 Stage 3.6 · Market breadth (2026-11-21, `docs/mark-1-build-plan.md` §3.6)

- [x] Universe `NIFTY50` = NSE Indices constituent file (fetched 2026-11-21) in `market_data/breadth/universe.py`; today's list is used for past dates (no survivorship correction); BSE and TMPV have no stored daily candles yet
- [x] Pure Polars computation (`market_data/breadth/compute.py`): A/D/unchanged vs previous stored close, new 52-week highs/lows (close basis, strict break of the previous 251 closes, needs 252 bars), % above EMA 50 / EMA 200 (`strategy.indicators` EMA), NIFTY / BANKNIFTY / INDIAVIX moves; hand-checked and hypothesis tests
- [x] Active provider's daily candles only; worker `compute_market_breadth` 16:25 IST (first run back-fills 60 sessions, later runs recompute the last 10 so late candles are picked up), `rebuild_market_breadth(from, to)`; API `GET /market/breadth`, `GET /market/breadth/latest`, `POST /market/breadth/rebuild` (owner)
- [x] Web: breadth tile on the dashboard (A/D bar, % above EMA 200/50, 52w highs/lows, index moves, date + provider), history chart on `/scanner`
- [x] Verified live (Upstox): 56 sessions 2026-08-27 → 2026-11-17; 2026-11-17: 48 members, 27 advances / 21 declines, 4 new 52w highs, 68.75 % above EMA 200, NIFTY +0.38 %; A/D cross-checked with SQL
- [ ] AI-MIOS 10-year history import (optional) and `avg_news_sentiment` (Stage 4)

## Mark 1 Stage 3.1 · Protocol engine (2026-11-21, `docs/mark-1-build-plan.md` §3.1)

- [x] Package `packages/protocols` (import contract: never imports apps or `ai`): `ActionRegistry` (name, description, risk green/yellow/red, Pydantic args, async fn → JSON); actions `health_check`, `broker_sessions`, `regime_summary`, `pcr_now` (with source/demo and freshness), `paper_status`, `todays_events`, `recent_alerts` (green), `kill_switch_on`, `stop_paper_strategies`, `close_paper_positions` (yellow; paper standing permission). No red action exists yet; validation refuses a red action unless the protocol has `confirm_required`
- [x] `close_paper_positions` requests the trader's square-off (stops the owning activation with flatten; the trader closes through the execution simulator) and fails honestly when the trader is not running; it never reports a fill
- [x] Shared services: `core.services.paper.stop_activation` (used by `POST /paper/activations/{id}/stop` and protocols), `core.services.audit.write_audit` (`api.audit.audit` delegates)
- [x] Runner: ordered steps, per-step savepoint, `on_error` stop/continue, results `{tool,args,status,started_at,finished_at,result|error}`, final succeeded/partial/failed; cancel honoured between steps; run stores its planned steps at creation, so a confirmed plan is exactly what runs
- [x] Built-ins seeded idempotently (version bump on change): market_open, market_close, shutdown (asks first), clean_slate (immediate kill switch), health_check, review
- [x] API `/protocols` (list, actions, create/update/delete owner-only, run, runs, run, confirm owner-only, cancel), audit rows; worker job `run_protocol(run_id)`
- [x] Web `/protocols`: risk badges per step, Run, confirm/cancel, run history with stored results, owner JSON step editor checked against `/protocols/actions`
- [x] Tests: registry validation, red-without-confirm, runner order/on_error/cancel, DB tests (seed, confirm flow, shutdown, close positions, clean slate, health/market open)
- [x] Checked live (Saturday): health_check and market_open executed by the worker; missing collector/trader/chains reported as missing
- [ ] Verify with the API from the browser as the owner (dev auto-login is off locally); layouts (`layout` column) unused until section 4

## Mark 1 Stage 3.2 · Proactive alerts (2026-11-21, `docs/mark-1-build-plan.md` §3.2)

- [x] `protocols.alerts`: pure rules `pcr_near_limit` (ALERT_PCR_MARGIN), `feed_stale`, `broker_session`, `daily_loss_near`, `kill_switch_active`, `trader_down`; `dedup` window (ALERT_DEDUP_MINUTES)
- [x] `protocols.alert_store`: facts from Redis/DB, store with dedup, Telegram delivery recorded in `delivered` (sent/skipped/failed; `pending` from the trader, delivered by the next job run)
- [x] Worker cron `evaluate_alerts` every minute, job checks 09:00–15:45 IST on NSE trading days
- [x] Trader: `signal_fired` alert after a paper order is submitted, `rule_block` alert when an owner rule blocks a signal (savepoint; trading behaviour unchanged)
- [x] API `/alerts` (since, unacknowledged, kind), `/alerts/{id}/ack`, `/alerts/ack-all`, `/alerts/unread-count`; web bell in the top bar and `/alerts` page
- [x] Tests: every rule, hypothesis properties (PCR alert iff within margin/beyond; dedup never stores a key twice inside the window), DB dedup + delivery
- [ ] Watch a real session (alerts on a trading day, Telegram once configured)

## Mark 1 Stage 3 · Storage, evening brief, candle refresh (2026-11-21)

- [x] Migration 0014: `protocols`, `protocol_runs`, `alerts`, `news_items`, `ingest_errors`, `market_breadth`, `daily_reports` (Text + CHECK instead of Postgres enums; migration tests incl. models-match and clean downgrade pass)
- [x] Evening brief (§3.3 + §3.7, no AI): `worker.reports.evening_brief` (pure build + markdown render, unit + property tests) and job `generate_evening_brief` at 19:00 IST on trading days: index closes and change vs previous daily close, PCR at close, NIFTY 50 breadth, paper accounts (trades, wins, net, open positions, cash), alerts by severity and owner-rule blocks, 1-minute completeness per collected symbol, next session and expiries within 7 days, headlines. Stored per day in `daily_reports` (regeneration replaces it), sent to Telegram when configured. API `GET /reports/daily`, `/reports/daily/latest`, `/reports/daily/{day}`, `POST /reports/daily/generate` (owner, enqueues). Web: "Evening brief" panel on `/reports` with day picker and Regenerate. Every missing source is printed as missing
- [x] Found while building it: nothing refreshed stored candles after a session (`eod_gap_report` only reports), so daily candles for 18-20 Nov were never fetched and the brief, regime, scanner and breadth ran on stale days. New job `refresh_daily_candles` at 15:45 IST: re-fetches the last 10 days of 1d candles for every instrument with daily history, every NIFTY 50 member and the indices, plus the last 3 sessions of official 1-minute candles for the collector's symbols (repairs collector downtime). Single provider, idempotent upserts
- [ ] `refresh_daily_candles` not yet run for real: the Upstox token had expired (Saturday, no login). Run it after the next broker login; breadth then recomputes 18-20 Nov automatically
- [ ] Evening brief not yet seen with a full live session's data, nor delivered to Telegram (no bot token)

