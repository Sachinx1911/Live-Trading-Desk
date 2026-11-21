# Mark 1 build plan: JARVIS, stage by stage

Owner request, 2026-11-21: "JARVIS che working chalu kar … proper detailed madhe planning kar".
This turns `docs/mark-1-plan.md` §3.3 (five stages) into work packages tied to the code as it
is today. It is a plan; each stage still starts on the owner's go-ahead (plan §9).

Rules that apply to every package: CLAUDE.md safety rules 1–9, ADR-009 (LLM boundary), the
owner rules in `docs/trading-rules.md`, tests with every module (hypothesis for risk, backtest
and order-state invariants), `docs/progress.md` updated when a package is done, every schema
change an Alembic migration (next free number: **0013**).

## 0. What the code already gives us

| Area | Today | Consequence for the plan |
|---|---|---|
| Option-chain history | `option_chain_snapshots` hypertable (migration 0006): one row per underlying + expiry + time, `rows` JSONB with per-strike `ltp, volume, oi, iv, delta, theta, gamma, vega` for calls and puts; collector writes every `COLLECT_CHAIN_INTERVAL_S` (180 s); compressed after 30 days | **Intraday OI history is already being recorded.** Stage 1 adds a derived per-strike table and queries, not a new collector |
| Chain API | `GET /market/option-chain` (latest), `/market/option-chain/expiries`; helpers `oi_totals`, `latest_chain_oi` in `market_data/repo/chains.py` | Extend with "snapshot at time T" and "change between T1 and T2" |
| Chain UI | `/market/option-chain` page, `components/market/OptionChainTable.tsx` (no Greeks columns) | Greeks view = new columns + toggles on the same table, built as a panel |
| Upstox provider | Candles, quotes, option contracts, chain; no expired-instrument endpoints | Back-fill needs a new provider method set (Upstox Plus) |
| Strategy DSL | `oi` available as a candle field; no PCR, OI change or Greeks features | Stage 2 adds them as DSL features |
| Owner rule 1 `pcr_guard` | Runs live/paper; returns `skipped` in backtest/replay ("no option-chain history in this mode") | Stage 2 feeds chain history to backtest/replay so the rule is enforced there too |
| AI layer | `packages/ai`: `LLMProvider`, OpenAI adapter, budgets, `ai_calls` log, NL builder, eval harness | Reused as is for JARVIS in Stage 4 |
| Notifications | Telegram notifier exists for alerts | Stage 3 alerts reuse it |

## 1. Stage 1 · Option data (no AI)

Goal: the owner can see how OI built up during any day and the Greeks per strike, on data we
store ourselves.

### 1.1 Derived per-strike OI table

- Migration **0013** `option_strike_series` (hypertable, derived, rebuildable from
  `option_chain_snapshots`): `underlying_instrument_id, expiry, ts, strike, side (CE/PE), oi,
  oi_change_from_open, ltp, volume, iv, delta, gamma, theta, vega, provider_id`. PK
  `(underlying_instrument_id, expiry, strike, side, ts, provider_id)`.
- Writer: the collector writes the derived rows in the same step as the snapshot; a worker job
  `rebuild_strike_series(underlying, expiry, day)` rebuilds from raw (CLAUDE.md: derived data
  must be rebuildable).
- Day-open baseline: first snapshot at or after 09:15 IST (derived via exchange timezone,
  ADR-006); `oi_change_from_open` is null when no baseline exists, never guessed.
- Tests: rebuild equals live-written rows; property test: sum of per-strike OI equals
  `oi_totals` for the same snapshot.

### 1.2 OI Change API and chart

- `GET /market/oi-change?underlying_id&expiry&date&from&to` → per strike: call and put OI at
  `from` and `to`, change, totals, PCR at both ends, spot at both ends, snapshot times actually
  used (nearest stored snapshot, with the gap shown), `source` and `freshness`.
- Web panel `OiChangePanel` (route `/market/oi-change`, built as a standalone panel per plan
  §4): bar chart of put/call OI change by strike (Sensibull-style), time-window picker
  (presets: today so far, last 15 / 30 / 60 min, custom), strike range around ATM, totals
  strip (call Δ, put Δ, PCR start → end, spot start → end). Demo data keeps the DEMO badge.
- Honest states: no snapshots for that day, collector gap inside the window, market closed.

### 1.3 Greeks view

- Add IV, delta, gamma, theta, vega columns to `OptionChainTable` behind a column toggle;
  ATM row highlighted; values exactly as the provider sent them (no local Black-Scholes in
  Stage 1; if the provider omits a Greek, the cell shows "—").
- Optional "at time T" picker reading `option_strike_series`, so the Greeks of an earlier
  moment can be shown.

### 1.4 Expired-contract back-fill (needs Upstox Plus)

- Provider methods in `packages/providers/upstox/`: expired expiries list, expired option
  contracts for an expiry, historical candles for an expired contract (with OI).
- Worker job `backfill_expired_options(underlying, expiry, strikes=ATM±N, timeframe=1m)` as a
  `DataImportJob` (existing import pipeline, quality checks, append-only raw candles).
- First target: October 2026 NIFTY monthly and weekly expiries.
- Blocked until the owner switches to Upstox Plus; everything else in Stage 1 is not.

### 1.5 Done when

OI Change panel answers "what happened between 10:00 and 11:30 today" from stored data;
Greeks visible on the chain; rebuild job matches live rows; progress.md updated; verified
once in a live session (cadence gap recorded, plan open decision 2).

## 2. Stage 2 · Option data inside backtest and replay (no AI)

- **Chain feed for simulations:** `market_data` gets a reader that serves, for a simulated
  time `t`, the latest chain snapshot with `ts <= t` (no look-ahead; property test that no
  returned snapshot is newer than `t`). Shared by backtest, replay and paper (ADR-002: one
  code path).
- **DSL features** (new DSL minor version, approved versions stay untouched): `pcr(expiry=near)`,
  `oi_change(strike=ATM±k, side, window)`, `option_greek(strike=ATM±k, side, greek)`, `iv_atm`.
  Missing data → feature is `null` → condition false, and it is reported in the run log.
- **Owner rule 1 in simulations:** `pcr_guard` gets the market context from the chain feed
  instead of returning `skipped`; backtest reports list every block it caused.
- **Next owner rules:** each new rule the owner gives is added to `owner_rules.py` with its
  tests and a row in `docs/trading-rules.md` (Red to apply; never optional per strategy).
- Done when a backtest over days that have chain history shows PCR-based entries and
  `pcr_guard` blocks, and days without history are flagged, not silently traded.

## 3. Stage 3 · Protocols, alerts, reports, Dhan (no AI)

### 3.1 Protocol engine (trading protocols)

- Package `packages/protocols` (new). Since the 2026-11-21 decision (Stage 4, option A) the
  domain-agnostic assistant core is the owner's jarvis, so protocols here are trading
  protocols; each still carries `domain="trading"` and is exposed as a tool in Stage 4.
- A protocol = a named, versioned list of tool calls with arguments and an optional screen
  layout, stored as JSON (no code; CLAUDE.md rule 4). Migration **0014** `protocols`,
  `protocol_runs` (append-only, step results).
- Built-in protocols from plan §2.4: Market Open, Market Close, Shutdown (asks first), Clean
  Slate (immediate kill switch on), Health Check, Review. Runnable from a button and from the
  API; in Stage 4 JARVIS calls the same thing.

### 3.2 Proactive alerts (EDITH without AI)

- Worker job every minute during market hours: rule about to trigger (e.g. PCR within X of the
  `pcr_guard` threshold), feed / collector down, signal fired, loss limit near. Each alert has
  a type, severity, data reference and dedup key. Delivered in-app and via the existing
  Telegram notifier. Migration **0015** `alerts`.

### 3.3 Reports

- End-of-day report (positions, paper P&L, rule blocks, data completeness, tomorrow's
  expiries) and trade review, generated by worker jobs, stored, shown on `/reports`.

### 3.4 Dhan

- `packages/providers/dhan/` (Access Token mode) as second broker and backup data source;
  token entered on `/settings/brokers`, encrypted (rule 8). Paper/live isolation unchanged.

### 3.5 News pipeline (from AI-MIOS v1)

Source: the owner's earlier project, `references/sachinx1911-stock-market-prediction-software.md`.

- Ingest (no AI, worker job every 30 min, 07:00–22:30 IST): RSS feeds that worked there
  (Moneycontrol Markets and Business, Economic Times Markets, LiveMint Markets); dedup by URL;
  store title, URL, source, published time and feed summary only (no article bodies).
  Migration: `news_items` (raw, append-only) + `ingest_errors` for dead feeds.
- Analysis is AI and therefore **waits for Stage 4** (OpenAI key): a News Analyst prompt under
  ADR-009 (batched JSON, fixed tag vocabulary = our instruments, sectors and a small macro
  list, invalid items skipped, daily budget). Result in a separate derived table
  `news_analysis` (sentiment by market impact, materiality, tags, `ai_call_id`), rebuildable.
- Until then the raw feed is already useful: `/news` page, news per symbol on the market
  screen, "today's headlines" in the Market Open protocol.
- Alerts (3.2): high-materiality news on a tracked symbol becomes an EDITH alert once analysis
  exists.

### 3.6 Market breadth (from AI-MIOS v1)

- Daily derived table `market_breadth` per trading day (IST): advances, declines, unchanged,
  52-week highs and lows, % of NIFTY 50 above EMA 200, index moves; later `avg_news_sentiment`.
  Computed by a worker job after the close from our stored daily candles; rebuildable.
- Back-fill: AI-MIOS has 10 years of validated NIFTY 50 daily data (128,000 candles) in its
  own database on the MacBook. Export it to CSV and bring it in through our existing import
  pipeline (`DataImportJob`, quality checks, append-only), instead of downloading again.
- Used by the market regime module, the NIFTY 50 heatmap panel (design image 11) and the
  daily report.

### 3.7 Daily report becomes the evening brief

- 3.3's end-of-day report gets the AI-MIOS brief structure, filled **without AI** in Stage 3:
  index moves, breadth, positions, paper P&L, rule blocks, data completeness, tomorrow's
  expiries, top headlines. Sent to Telegram at about 19:00 IST on trading days (NSE holiday
  calendar; compare our calendar with AI-MIOS `nse_holidays_2026.json`).
- In Stage 4 JARVIS adds a written view on top, following 4.6.

Owner supplies: Dhan access token, Telegram bot token.

## 4. Stage 4 · JARVIS reads and talks (AI, read-only)

**Decision (owner, 2026-11-21): option A, connect.** The JARVIS is the owner's existing
assistant, `Sachinx1911/jarvis` (`references/sachinx1911-jarvis.md`): it already has the agent
loop, memory, approvals, kill switch, Telegram, Marathi voice and a dashboard. Live-Trading-Desk
does **not** build a second assistant core. It stays the trading engine and exposes its actions
as a **tool server**; the owner's jarvis gets a trading workspace that calls those tools.

Split of responsibility:

| Live-Trading-Desk (this repo) | Owner's jarvis (`Sachinx1911/jarvis`) |
|---|---|
| Market data, option chains, strategies, backtest, replay, paper trading, risk engine, owner rules, execution gateway, alerts, reports, protocols | Conversation, memory, voice, Telegram, approvals UI, agent loop, modes (JARVIS / FRIDAY / EDITH narration / KAREN), schedules, briefs |
| Decides what each tool may do and enforces it server-side | Decides which tool to call and asks the owner when its tier requires |
| Holds broker secrets; they never leave this repo | Holds only a scoped tool-server token (Keychain) |

Needs: nothing from OpenAI for the tool server itself. jarvis uses its own model (Claude today).
OpenAI under ADR-009 stays for AI that runs inside Live-Trading-Desk (NL builder, News Analyst).

### 4.1 Tool server (this repo)

- New app `apps/tool_server` (or a router set in `apps/api`, decided at build time) speaking
  **MCP**, with a typed HTTP fallback generated from the same definitions.
- Each tool: `name, domain="trading", description (EasyTool style: one purpose line + one
  example), input schema (Pydantic), output schema, level Green/Yellow/Red, jarvis tier, timeout`.
- Level → jarvis tier mapping: **Green → T0** (run), **Yellow paper (standing permission) → T1**
  (run, report), **other Yellow → T2** (ask first), **Red → not exposed at all**. The tool server
  refuses anything above the level the stage allows, whatever the caller claims.
- Stage 4 exposes **Green tools only**: quotes, candles, option chain, OI change, Greeks, regime,
  breadth, scanner results, backtest results, positions, paper P&L, health, alerts, reports,
  news headlines, protocol status.
- Every response carries `source`, `freshness` and `is_demo` (CLAUDE.md rule 5); jarvis must
  repeat them, never present demo data as live.
- Auth: one service token per jarvis install, scoped to the tool server, stored encrypted here
  and in the Keychain there; loopback or LAN only, rate-limited, revocable from
  `/settings`. Migration: `tool_calls` (append-only authority log: tool, args, level, caller,
  result reference, duration). jarvis keeps its own audit too.
- Kill switch: a jarvis `/stop` or "Clean Slate" maps to the existing kill-switch endpoint,
  which only ever turns trading **off** (turning it back on stays Red, owner in our UI).
- Tests: every tool has a contract test; property test that no tool above the allowed level is
  callable; secret-scan test that no response contains broker credentials.

### 4.2 jarvis side (work in the owner's jarvis repo, its own sessions and commits)

- Connector `trading` in jarvis's connector registry pointing at the tool server, with health
  check and the tier mapping above.
- A trading workspace (loka) with its own memory folder, budget and constraints file; the owner
  rules and "no orders from an LLM" go into its `constraints.md`, so they are always in the prompt
  (the tool server still enforces them; the prompt is a second line, not the first).
- Modes: FRIDAY behaviour (short answers) during NSE market hours as a skill / SOUL addition;
  KAREN as the review skill.
- EDITH: Live-Trading-Desk's alert engine (3.2) pushes alerts to jarvis (webhook or event
  stream); jarvis only narrates and forwards them (Telegram, voice). Alerts are never generated
  by the model.
- Morning and evening brief: jarvis's brief gets a trading section from the tool server
  (3.7 report data).

### 4.3 Memory

- Trading notes, preferences and episodes live in **jarvis's memory** (the trading workspace).
  The Postgres `jarvis_*` tables from `docs/research/jarvis-memory-and-data-store.md` are
  **not built** here; that note is superseded by jarvis's memory design for everything except
  the principles (provenance, owner-owned, numbers always via tools).
- Live-Trading-Desk keeps only its domain data plus `tool_calls` and the accuracy log (4.6).

### 4.4 Screens and panels

- Live-Trading-Desk web screens are built as standalone **panels** with stable URLs (plan §4),
  so jarvis (or its macOS wrapper `mac/Jarvis`) can open a panel by URL with parameters.
- Screen manager (which monitor, resize, dissolve) belongs to the jarvis side; the Tauri shell
  planned here is dropped unless jarvis's wrapper cannot do it. To be designed with the HUD
  theme.

### 4.5 Command evaluation set

- 100+ real owner commands (Marathi, Hindi, English) with expected tool calls, scored like
  TaskBench (steps, tool choice, arguments). Lives in jarvis's evaluation suite, runs against a
  tool server with demo data.

### 4.6 Accuracy loop for JARVIS's views (from AI-MIOS v1)

The rule "every number from a tool" keeps JARVIS's facts honest; this keeps its **opinions**
honest.

- Whenever JARVIS states a direction (in chat, the evening brief or a review), the answer
  carries a structured stance: instrument, direction (up / down / sideways), horizon in
  trading days, confidence, and an **invalidation condition** ("view wrong below 23,800").
  Facts, news and JARVIS's own synthesis are labelled separately in the text.
- Each stance is recorded in Live-Trading-Desk through the `record_view` tool (it needs our
  prices to be scored) into `ai_observations` (append-only): stance, reference price taken by
  the tool server at that moment (with source and freshness), caller (jarvis or the internal
  brief), mode, time. jarvis's skill makes the call whenever it states a direction.
- A worker job scores matured observations against the actual close (single threshold
  constant, trading-day arithmetic, NSE holidays), writing the grade to a separate derived
  table; scores can be rebuilt.
- Page `/ai/accuracy`: hit-rate by instrument, horizon, mode and confidence band (is high
  confidence really more accurate?), plus AI spend. KAREN uses it in the Review protocol.
- The invalidation condition can be turned into an EDITH alert (Stage 3 alert engine) when
  price crosses it.
- Observations are **never** inputs to trading: no strategy, risk check or order reads them
  (ADR-009). They measure JARVIS, nothing more.
- Tests: property tests for the scoring function over the full direction × outcome matrix;
  trading-day arithmetic across weekends and holidays; scorer idempotent.

### 4.7 News analysis and the AI brief

- Turn on the News Analyst from 3.5 (inside Live-Trading-Desk, OpenAI via `call_structured`,
  budgets and `ai_calls`) and JARVIS's written view in the evening brief from 3.7 (written by
  jarvis from tool data). Open: whether news analysis also moves to jarvis (§7).

## 5. Stage 5 · JARVIS makes changes (Yellow tools)

- The tool server adds Yellow tools: run backtest / replay, create strategy draft or new
  version, start / stop / pause a paper strategy, close paper positions, run a protocol, create
  a rule *draft*, record a view (4.6).
- Paper standing permission (plan §2.3) = jarvis tier T1 (run, then report at once); other
  Yellow = T2 (ask first). "Stop" / "undo that" from jarvis works mid-plan.
- The tool server enforces paper-only for these tools: they cannot reach the live account,
  live tables or the live gateway (ADR-008), whatever arguments arrive.
- Multi-step plans are jarvis's planner; the tool server still checks each call on its own.
- Red actions are **never tools**: live orders, applying a hard rule, changing limits, kill
  switch off, live approval. jarvis can only open the right Live-Trading-Desk panel with the
  request prepared; the owner confirms there. Live orders stay in
  `packages/execution/live/gateway.py` behind its five gates (CLAUDE.md rules 1–2).
- Accuracy loop (4.6) extends to Stage 5 actions: when JARVIS runs a backtest or starts a
  paper strategy "because it expects X", that expectation is recorded and scored the same way.
- KAREN: trade reviews and teaching ("where do I see PCR?" opens the panel and highlights the
  control; no clicking in other apps).

## 6. Order, dependencies, where it can be built

| Package | Depends on | Owner input | Machine |
|---|---|---|---|
| 1.1 Strike series | — | — | Either |
| 1.2 OI Change chart | 1.1 | — | Either |
| 1.3 Greeks view | — (1.1 for "at time T") | — | Either |
| 1.4 Back-fill | Upstox Plus | Switch plan | Either |
| 2 Chain in simulations + DSL | 1.1 | Next rules | Either |
| 3.1 Protocol engine | — | — | Either |
| 3.2 Alerts | 3.1 | Telegram token | Either |
| 3.3 Reports | — | — | Either |
| 3.4 Dhan | — | Dhan token | Either |
| 3.5 News ingest (raw) | — | — | Either |
| 3.6 Market breadth | daily candles | AI-MIOS data export (optional back-fill) | Export on MacBook; rest either |
| 3.7 Evening brief (no AI) | 3.3, 3.5, 3.6 | Telegram token | Either |
| 4.1 Tool server (Green) | 1–3 tools worth exposing | — | Either |
| 4.2 jarvis connector + trading workspace | 4.1 | Work in the jarvis repo | Either (jarvis runs on both) |
| 4.4 Panels by URL, screen manager | 4.1, design theme | — | Panels: either; screen manager: MacBook |
| 4.6 Accuracy loop | 4.1 (`record_view`), 3.2 for invalidation alerts | — | Either |
| 4.7 News analysis + AI brief | 3.5, 3.7, 4.2 | OpenAI key (news analysis here) | Either |
| 5 Yellow tools | 4.1, 4.2 | — | Either |

Suggested first step on go-ahead: **1.1 → 1.2 → 1.3** (no external input needed, immediately
useful on the market screen); 1.4 as soon as Upstox Plus is active.

## 7. Decisions needed and when

| Before | Decision |
|---|---|
| Stage 1 | Chain interval stays 3 minutes or back to 5 (plan §8 item 2); strike range kept in the derived table (all strikes or ATM ± N) |
| Stage 1.4 | Upstox Plus switched on |
| Stage 2 | The next owner trading rules |
| Stage 3 | Alert thresholds (how close counts as "about to trigger"); which news feeds; whether to import AI-MIOS's 10-year data; evening brief time (19:00 IST as in AI-MIOS?) |
| Stage 4.6 | Scoring threshold (AI-MIOS used ±1 %) and default horizons for JARVIS's views |
| Stage 4 | MCP only or MCP + HTTP; tool server reachable on loopback only or also LAN (jarvis on the same Mac?); whether news analysis stays here (OpenAI) or moves to jarvis (Claude); HUD as a third theme or replacing the TradingView themes; cyan-first or amber-first palette; what stays on screen 2 |
| Stage 5 | Confirm the paper standing-permission scope once more with real examples |
