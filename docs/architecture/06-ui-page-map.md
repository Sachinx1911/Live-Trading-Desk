# 06 · UI Page Map and Design System

Companion to `docs/MASTER_PROMPT.md` §6 and the ADRs. This document defines what the
frontend (`apps/web`) looks like, how it is organised, and which screens ship in which
phase. It is the contract between backend routes and frontend pages.

---

## 1. Design system

### 1.1 Direction

A premium quantitative trading terminal, not an admin dashboard. Dense, dark, calm. Colour
is used for *meaning* (P&L sign, data freshness, paper vs live, AI origin), never for
decoration. Motion is minimal: state changes fade, nothing bounces.

### 1.2 Colour tokens

Defined once as CSS variables in `apps/web/styles/tokens.css` and mirrored in the Tailwind
config. Components never use raw hex values.

| Token | Value (reference) | Use |
|-------|-------------------|-----|
| `--bg-app` | `#0B1020` | Application background (dark navy) |
| `--bg-panel` | `#06080F` | Panel / card surfaces (deep black) |
| `--bg-panel-raised` | `#0F1526` | Hovered or focused panels, popovers |
| `--border-subtle` | `#1B2338` | Panel borders, dividers (1px) |
| `--border-strong` | `#2A3550` | Focused inputs, active tabs |
| `--text-primary` | `#E6EAF2` | Body text, numbers |
| `--text-secondary` | `#8B95AD` | Labels, captions |
| `--text-muted` | `#55607A` | Placeholders, disabled |
| `--accent-cyan` | `#22D3EE` | Primary actions, active nav, selection, links |
| `--accent-cyan-dim` | `#0E7490` | Cyan at rest / outlines |
| `--accent-ai` | `#A78BFA` | Anything produced by an LLM: badges, borders, AI panels |
| `--accent-ai-dim` | `#5B21B6` | AI backgrounds at low alpha |
| `--pnl-positive` | `#22C55E` | Profit, up moves, long |
| `--pnl-negative` | `#EF4444` | Loss, down moves, short |
| `--state-live` | `#22C55E` | Data state: Live |
| `--state-delayed` | `#F59E0B` | Data state: Delayed |
| `--state-disconnected` | `#EF4444` | Data state: Disconnected |
| `--state-demo` | `#A78BFA` striped | Data state: Demo / synthetic |
| `--mode-paper` | `#38BDF8` | Paper trading tag and borders |
| `--mode-live` | `#FB7185` | Live trading tag and borders |

Rules:
- Green and red are reserved for P&L direction and Live/Disconnected state. Never use them
  for buttons or decoration.
- Purple (`--accent-ai`) marks every piece of LLM output. A user must always be able to tell
  AI text from system data at a glance.
- Paper and live tags appear on every order, position, account and activation, everywhere.

### 1.3 Typography

- UI font: Inter (or system UI stack). Monospace for ids, codes, DSL JSON: JetBrains Mono.
- **All numbers use tabular numerals** (`font-variant-numeric: tabular-nums`) so columns align.
- Indian number formatting is the default for INR: `₹1,00,000.00`, `₹12,34,567`. A single
  `formatMoney(value, currency, market)` helper handles grouping per market (US markets use
  `1,000,000`). Never format money inline.
- P&L is always shown with sign and colour: `+₹2,450.00` green, `−₹1,120.50` red. Zero is
  neutral grey.
- Percentages to 2 decimals, prices to the instrument's tick precision.
- Timestamps display in the selected market's timezone with an explicit zone suffix
  (`14:32:05 IST`). Storage is UTC (ADR-006).

### 1.4 Spacing and layout

- 4px base grid. Panels have 12px padding, 8px internal gaps, 1px subtle border, 6px radius.
- Desktop-first. Minimum supported width 1280px for trading screens; 1024px degrades to a
  single column; below that, only read-only pages (dashboard, portfolio, journal) are
  supported.
- Fixed left sidebar (collapsible to icons at 56px, expanded 224px). Top bar carries market
  selector, session clock, provider status pill, broker session pill, kill-switch button
  (live only), user menu.
- Dense tables (`32px` rows), sticky headers, virtualised beyond 200 rows.

### 1.5 Mandatory data-state badges

Every panel that shows market-derived numbers carries one badge. The backend supplies the
state; the frontend never infers "live" from the presence of a number.

| Badge | Meaning | Visual |
|-------|---------|--------|
| **Live** | Streaming, last event < 5s old | Solid green dot, pulsing |
| **Delayed** | Last event 5s–120s old, or provider marked delayed | Amber dot, age shown (`12s`) |
| **Disconnected** | No feed, token expired, provider down | Red dot, panel numbers greyed, reason text |
| **Demo** | Synthetic or fixture data, non-production | Purple striped banner across panel top, label "DEMO DATA" |
| **Historical** | Backtest/replay context, timestamp shown | Grey clock icon with date |

Rules (from master prompt §6 and CLAUDE.md rule 5):
- No numeric value is rendered without a state. Loading shows skeletons, never zeros.
- Disconnected panels keep the last known values visible but greyed with the last-seen time;
  they never silently continue to animate.
- Demo mode is a build-time/user-setting flag; it cannot be enabled on the live trading pages.

### 1.6 Component inventory (shadcn/ui base + custom)

Custom components live in `apps/web/components/trading/`:

- `DataStateBadge`, `ModeTag` (paper/live), `AiBadge`
- `Money`, `Pct`, `Price`, `Delta` (formatted, coloured numerics)
- `MarketChart` (Lightweight Charts wrapper: candles, volume, indicator overlays as series,
  trade markers, replay cursor)
- `EquityCurve`, `DrawdownChart`, `MetricTile`
- `OrderTable`, `PositionTable`, `TradeTable` (virtualised)
- `OptionChainGrid`
- `StrategyRuleTree` (renders DSL AND/OR tree), `DslJsonViewer`
- `ProviderStatusPill`, `BrokerSessionPill`, `KillSwitchButton`
- `ApprovalCard`, `ClarificationThread`
- `JobProgress` (WS-fed progress bar for backtests, research, imports)

---

## 2. Sidebar

The master prompt's 15 items are kept and grouped so the sidebar scans in under two seconds.
Each group header is collapsible; the collapsed state persists per user.

| Group | Items (master prompt name → route) |
|-------|------------------------------------|
| **Overview** | Dashboard → `/dashboard` |
| **Intelligence** | AI Trading Hub → `/ai-hub` · AI Learning → `/ai-learning` |
| **Strategy** | Strategy Center → `/strategies` |
| **Data** | Market Data → `/market` · Market Scanner → `/scanner` |
| **Trading** | Trading → `/trading` · Paper Trading → `/paper` · Live Trading → `/live` |
| **Research** | Backtesting → `/backtesting` · (Replay) → `/replay` |
| **Portfolio** | Portfolio & Analytics → `/portfolio` · Reports → `/reports` |
| **System** | Multi-Market → `/multi-market` · Tools → `/tools` · Settings → `/settings` |

Live Trading is rendered with the `--mode-live` tint and is hidden entirely until at least
one broker account is connected and the user has enabled live trading in Settings.

---

## 3. Page map

Format per route: **Purpose · Panels · Data · States · Phase**. "WS" refers to channels on
the single authenticated WebSocket `/ws` (see `04-api-spec.md`). Endpoint paths are
indicative and are authoritative in the API spec.

### 3.1 Auth

#### `/login`
- **Purpose:** Email + password sign-in, optional TOTP step.
- **Panels:** Centered card, product mark, form, error banner.
- **Data:** `POST /auth/login`, `POST /auth/totp/verify`.
- **States:** idle, submitting, invalid credentials, TOTP required, locked out.
- **Phase:** 1.

#### `/logout`, `/auth/refresh` (silent)
- Token refresh via rotating refresh token cookie. No UI. **Phase 1.**

No public sign-up in v1 (ADR-014); the owner is created by CLI.

### 3.2 Overview

#### `/dashboard`
- **Purpose:** One screen that answers "is everything connected, what regime is it, am I
  inside my limits, what needs my approval."
- **Panels:**
  1. Index strip: NIFTY, BANKNIFTY, SENSEX, India VIX with change, each with a data-state badge.
  2. Market selector + session clock (pre-open / open / closed / holiday, from trading calendar).
  3. Provider status: active provider, mode (single/comparison/failover), feed latency, last tick age.
  4. Broker session status: token valid until, "Login now" action when expired (ADR-012).
  5. Risk gauge: daily loss used vs limit (percentage bar, no rupee figure by default; toggle to reveal).
  6. Market chart (selected index, 5m default).
  7. AI Market Insights (morning brief, purple-bordered, with "generated at" and model).
  8. Active strategies (mode tag, regime filter state, signals today).
  9. Running trades (paper and live sections, separately).
  10. Daily P&L and win rate (per mode).
  11. Portfolio overview (capital, exposure, margin).
  12. Multi-market status (one row per enabled exchange).
  13. AI research activity (jobs running / queued, token spend today).
  14. Strategy approval queue (count + first three cards).
  15. AI learning insights (latest trade reviews).
- **Data:** `GET /dashboard/summary`, `GET /providers/status`, `GET /brokers/sessions`,
  `GET /risk/status`, `GET /strategies/activations`, `GET /approvals?status=pending`,
  `GET /ai/briefs/latest`; WS channels `quotes:index`, `provider.status`, `risk.status`,
  `orders.*`, `jobs.*`.
- **States:** Each panel independent. Loading = skeleton. Disconnected = greyed values with
  reason ("Upstox token expired at 03:30 IST"). Empty = "No active strategies" with a link.
  Demo = striped banner. **Never a fabricated number**: if `GET /dashboard/summary` returns
  `null` for a field, the tile shows an em-dash and the state badge.
- **Phase:** 1 (shell: panels 2, 3, 4, 12 real; all others rendered as explicit
  "Not available yet / Disconnected" tiles). Filled progressively in Phases 2–6.

### 3.3 Intelligence

#### `/ai-hub`
- **Purpose:** Home of the AI Trading Agent and AI Market Analysis (Modules 1, 2, 6).
- **Panels:** Morning Brief (regime, levels, bias, risk flags, recommended strategy set);
  Regime timeline (deterministic detector vs LLM narrative side by side, detector wins);
  Opportunity list (trade setups with explanation, "stay out" recommendation visible);
  Analysis workspace per instrument (structure, S/R, volume profile, OI levels, momentum);
  Token spend and budget for today.
- **Data:** `GET /ai/briefs`, `GET /ai/regime`, `GET /ai/setups`, `POST /ai/analyze`,
  `GET /ai/usage`; WS `ai.jobs`.
- **States:** No brief yet (before 08:30 or job failed) shows explicit "Brief not generated"
  with the job error. Every AI panel carries the AI badge and `generated_at`.
- **Phase:** 6 (regime detector from Phase 4 is shown earlier on the dashboard).

#### `/ai-learning`
- **Purpose:** Module 5 and the AI learning workflow (§8).
- **Panels:** Completed trade reviews (filter by strategy, mode, outcome); Winning vs losing
  trade analysis (pattern clusters); Market regime insights; Improvement suggestions, each
  linked to the evidence trade ids and backtest ids; Candidate strategy versions pipeline
  (draft → backtested → OOS validated → paper → awaiting approval); Approval status.
- **Data:** `GET /ai/reviews`, `GET /ai/recommendations`, `GET /strategies/versions?status=candidate`,
  `GET /approvals`; WS `ai.jobs`, `jobs.backtest`.
- **States:** Empty until trades complete. Candidates without passing OOS results are shown
  with a red "Not validated" chip and cannot be approved from here.
- **Phase:** 6.

### 3.4 Strategy

#### `/strategies` (Library)
- **Purpose:** Module 10. Every strategy, every version, its status and performance.
- **Panels:** Filter bar (origin: user/AI, category, status, instrument, timeframe); Table
  (name, latest version, status chip, mode activations, backtest summary, last changed);
  Side drawer preview of the DSL rule tree.
- **Data:** `GET /strategies`, `GET /strategies/{id}`.
- **States:** Empty state links to the three builders. Archived strategies hidden by default.
- **Phase:** 5 (read-only list of seeded test strategies appears in Phase 3 for paper trading).

#### `/strategies/new/natural-language`
- **Purpose:** Module 8, highest priority. Marathi / Hindi / English description → validated DSL draft.
- **Panels:** Left: description editor with language selector, market/instrument/timeframe
  pickers, example chips. Right: live preview of the generated DSL as a rule tree + JSON
  tab; Missing-information list; Clarification thread (AI questions, user answers, each
  turn stored); Validation results (schema, indicator availability, logical warnings such as
  "no exit condition"); Actions: Regenerate, Edit manually, Save as draft.
- **Data:** `POST /strategies/generate` (returns DSL + `missing_information` + questions),
  `POST /strategies/generate/{draft_id}/answer`, `POST /strategies/validate`, `POST /strategies`.
- **States:** Generating (streamed), Needs clarification (highlighted), Invalid (schema errors
  listed inline), Ready to save. The original description is pinned and never altered;
  any AI change to a condition is highlighted as a diff the user must accept.
- **Phase:** 5.

#### `/strategies/new/visual`
- **Purpose:** Module 9. Build the same DSL by clicking.
- **Panels:** Indicator palette (fixed, versioned list); Condition builder rows
  (left operand, operator, right operand/value); AND/OR grouping tree; Entry / Exit / Stop /
  Target / Position sizing / Session rules tabs; Regime filter; Live JSON preview; Validate.
- **Data:** `GET /strategies/dsl/schema`, `GET /indicators`, `POST /strategies/validate`, `POST /strategies`.
- **States:** Draft autosaved locally; server validation errors anchored to the offending row.
- **Phase:** 5.

#### `/strategies/[id]`
- **Purpose:** Single strategy detail.
- **Panels:** Header (name, origin, category, latest version, status); Rule tree; Parameters;
  Backtest results summary with link to runs; Activations (paper/live) with mode tags;
  Performance history chart (per version); Notes; Actions: Clone, New version, Run backtest,
  Request approval, Activate (paper), Archive.
- **Data:** `GET /strategies/{id}`, `GET /strategies/{id}/versions`, `GET /backtests?strategy_id=`,
  `GET /strategies/{id}/activations`.
- **States:** Approved versions are read-only with a lock icon; editing forks a new draft version.
- **Phase:** 5.

#### `/strategies/[id]/versions`
- **Purpose:** Version history and diff.
- **Panels:** Version list (number, status, author user/AI, created, evidence links); Side-by-side
  DSL diff; Per-version backtest metrics; Promote / demote actions respecting the approval workflow.
- **Data:** `GET /strategies/{id}/versions`, `GET /strategies/versions/{vid}/diff?against=`.
- **Phase:** 5.

#### `/strategies/compare`
- **Purpose:** Module 24. Compare N strategies/versions on identical data and costs.
- **Panels:** Picker (up to 6 versions); Shared assumptions form (instrument set, date range,
  costs, slippage) that is applied to all; Metrics table; Overlaid equity curves; Drawdown
  comparison; Monthly return heatmap.
- **Data:** `POST /backtests/compare` (creates a comparison job), `GET /backtests/compare/{id}`; WS `jobs.backtest`.
- **Phase:** 4 (engine) / 5 (UI).

#### `/strategies/approvals`
- **Purpose:** Approval workflow for paper → live and for AI candidate versions.
- **Panels:** Queue of `ApprovalCard`s (what changed, evidence: backtest, OOS, paper period
  stats, risk assessment); Required checklist (backtest passed, OOS passed, paper ≥ N days,
  risk limits configured); Approve for paper / Approve for live (live requires re-entering
  password and typing the strategy name); Reject with reason.
- **Data:** `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`.
- **States:** Cards missing any checklist item have the live button disabled with the reason.
- **Phase:** 5 (paper approvals), 10 (live approvals enabled).

### 3.5 Data

#### `/market` (Watchlist + Chart)
- **Purpose:** Module 12 live view.
- **Panels:** Watchlists (user-defined, up to 100 symbols); Quote table (LTP, change, bid/ask,
  volume, OI, state badge per row); Main chart (timeframe switcher, indicators as overlays,
  drawing not supported in v1); Depth panel (5 levels; 20/30 when provider supports);
  Instrument search (instrument master).
- **Data:** `GET /instruments/search`, `GET /watchlists`, `GET /candles`, WS `quotes:{instrument_id}`,
  `depth:{instrument_id}`.
- **States:** Per-row state. When the provider is disconnected the whole table shows the
  last-seen time banner.
- **Phase:** 2.

#### `/market/option-chain`
- **Purpose:** Module 14.
- **Panels:** Underlying + expiry selectors; `OptionChainGrid` (CE | strike | PE with LTP,
  change, OI, ΔOI, volume, IV, Greeks when available or calculated with a "calc" marker);
  PCR, max pain, OI buildup summary; Snapshot timeline scrubber (from stored 5-min snapshots).
- **Data:** `GET /options/chain`, `GET /options/snapshots`, WS `optionchain:{underlying}:{expiry}`.
- **States:** Greeks show "calc" vs "provider" source; missing IV cells show em-dash, not 0.
- **Phase:** 2 (live chain), 4 (snapshot history).

#### `/market/providers`
- **Purpose:** Module 11 and 15 — provider management UI.
- **Panels:** Provider cards (Upstox, Dhan, future): connection health, auth state, rate-limit
  usage, feed latency p50/p95, reconnects today; Mode switch (Single / Comparison / Failover)
  with confirmation; Historical coverage matrix (instrument class × timeframe × date range);
  Comparison report (price, timestamp, missing candles, duplicate events, volume diffs) with
  the caveat banner "Differences are not automatically errors".
- **Data:** `GET /providers`, `GET /providers/{id}/health`, `POST /providers/mode`,
  `GET /providers/coverage`, `GET /data-quality/reports`.
- **Phase:** 2 (Upstox card, coverage), 7 (Dhan, comparison, failover).

#### `/scanner`
- **Purpose:** Scan the instrument universe for conditions written in the same DSL.
- **Panels:** Scan definition (universe, timeframe, condition tree reusing the visual
  builder); Results table (instrument, triggered at, values); Save scan; Schedule scan.
- **Data:** `POST /scans`, `GET /scans/{id}/results`; WS `jobs.scan`.
- **Phase:** 5.

### 3.6 Trading

#### `/trading`
- **Purpose:** Trading overview across modes (Module 16/19).
- **Panels:** Activations table (strategy version, mode tag, instrument, status, signals today,
  P&L); Signal feed (latest signals and what the engine did with them: filled, rejected by
  risk, blocked by event, ignored out of session); Order lifecycle inspector (state machine
  timeline for any order id).
- **Data:** `GET /activations`, `GET /signals`, `GET /orders/{id}/events`; WS `signals`, `orders.*`.
- **Phase:** 3.

#### `/paper`
- **Purpose:** Module 17. Default landing shows the selected paper account.
- **Panels:** Account header (virtual capital, available balance, used margin, realized /
  unrealized P&L, mode tag Paper); Open positions; Open orders; Strategy-wise performance;
  Fill quality (slippage vs mid, spread paid, charges breakdown).
- **Data:** `GET /paper/accounts/{id}`, `GET /paper/positions`, `GET /paper/orders`,
  `GET /paper/performance`; WS `paper.orders`, `paper.positions`.
- **Phase:** 3.

#### `/paper/accounts`
- Create / edit paper accounts (name, initial capital default ₹1,00,000, cost profile,
  slippage model, reset). `GET/POST /paper/accounts`, `POST /paper/accounts/{id}/reset`. **Phase 3.**

#### `/paper/orders`
- Full order history with filters, state timeline, simulated fill details (bid/ask at fill,
  partial fills). `GET /paper/orders`. **Phase 3.**

#### `/paper/positions`
- Open and closed positions, per-position P&L curve, exit reasons. `GET /paper/positions`. **Phase 3.**

#### `/live`
- **Purpose:** Module 18. Rendered with the live tint. Hidden until enabled in Settings.
- **Panels:** Broker session banner (account, token valid until, "Login now" when expired —
  ADR-012); **Kill switch** (global / account / strategy, red, always visible, two-step
  confirm, shows who triggered it last and why); Daily and weekly loss limits with used
  percentage; Live activations (only `approved_live` versions can appear); Open positions
  and orders from the broker (reconciled; mismatches flagged in amber with "Reconciliation
  pending"); Order placement is **not** a free-form form — only strategy-driven orders and
  "flatten position" exist in v1; Reconciliation log.
- **Data:** `GET /live/accounts`, `GET /brokers/sessions`, `GET /live/positions`,
  `GET /live/orders`, `POST /live/kill-switch`, `POST /live/positions/{id}/flatten`,
  `GET /live/reconciliation`; WS `live.orders`, `live.positions`, `risk.status`, `killswitch`.
- **States:** Token expired → whole page is Disconnected with a single call to action.
  Any order whose state is not broker-confirmed is shown as "Submitted (unconfirmed)",
  never as filled (CLAUDE.md rule 6).
- **Phase:** 10 (gateway code lands in Phase 3 behind a feature flag; UI enabled in Phase 10
  after live validation).

### 3.7 Research

#### `/backtesting`
- **Purpose:** Module 21 workspace landing: recent jobs.
- **Panels:** Jobs table (strategy version, instruments, range, timeframe, status, key
  metrics); New backtest button.
- **Data:** `GET /backtests`; WS `jobs.backtest`.
- **Phase:** 4.

#### `/backtesting/new`
- **Panels:** Strategy version picker; Instrument(s) picker; Date range with data-coverage
  hint (greyed ranges where candles are missing); Timeframe; Initial capital; Cost profile
  (brokerage plan, STT, exchange, GST, stamp duty — defaults from `cost_schedules`); Slippage
  and spread model; Execution delay; Seed; Walk-forward / OOS split options; Run.
- **Data:** `GET /providers/coverage`, `GET /cost-profiles`, `POST /backtests`.
- **States:** Validation prevents running on ranges with < 95% candle coverage unless
  the user ticks "I understand gaps exist".
- **Phase:** 4.

#### `/backtesting/[jobId]`
- **Panels:** Metric tiles (total return, CAGR, win rate, profit factor, max DD, Sharpe,
  Sortino, Calmar, expectancy, avg win/loss, total trades, exposure time); Equity curve
  with drawdown underlay; Trade list with per-trade MAE/MFE; Monthly returns heatmap;
  Parameter and assumptions panel (frozen, for reproducibility); Walk-forward windows table;
  Actions: Re-run with same seed, Compare, Open in Replay, Create candidate version.
- **Data:** `GET /backtests/{id}`, `GET /backtests/{id}/trades`, `GET /backtests/{id}/equity`.
- **States:** Running shows streamed progress; failed shows the engine error and the data
  gaps detected.
- **Phase:** 4 (optimisation and sensitivity panels added late Phase 4).

#### `/replay`
- **Purpose:** Module 22.
- **Panels:** Session picker (instrument, date); Chart with replay cursor; Controls (play,
  pause, speed ×1 ×5 ×20, step forward/back by one bar); Optional strategy overlay showing
  signals and simulated fills as the session replays; Event log.
- **Data:** `POST /replay/sessions`, WS `replay:{session_id}` (server-driven clock).
- **Phase:** 4.

### 3.8 Portfolio

#### `/portfolio`
- **Purpose:** Modules 25 and 26.
- **Panels:** Capital summary per mode and account; Holdings and positions; Exposure by
  instrument / sector / strategy; Margin (available, used); Performance (daily, weekly,
  monthly) with strategy-wise and instrument-wise breakdown; Risk report (drawdown,
  VaR-lite, correlation matrix of active strategies).
- **Data:** `GET /portfolio/summary`, `GET /portfolio/snapshots`, `GET /analytics/performance`,
  `GET /analytics/risk`.
- **Phase:** 3 (paper), 6 (full analytics).

#### `/reports`
- **Purpose:** Exportable reports and the trading journal (Module 27).
- **Panels:** Journal (every trade: strategy version, entry/exit reason, regime, P&L, risk,
  AI review in purple, user notes editable); Daily review form (the three fixed questions);
  Report builder (period, mode, strategy) → PDF/CSV export; Rule-violation log.
- **Data:** `GET /journal`, `PATCH /journal/{trade_id}/notes`, `POST /reports/export`.
- **Phase:** 3 (journal), 6 (AI review column), 10 (export polish).

### 3.9 System

#### `/multi-market`
- **Purpose:** Module 28.
- **Panels:** Exchange cards (NSE, BSE, MCX, US, …): enabled flag, timezone, session rules,
  current session state, trading calendar preview, instrument master status, currency;
  Add exchange adapter (only those implemented appear).
- **Data:** `GET /exchanges`, `GET /exchanges/{id}/calendar`, `PATCH /exchanges/{id}`.
- **Phase:** 1 (NSE card, read-only), 9 (others).

#### `/tools`
- **Purpose:** Utilities that don't belong elsewhere.
- **Panels:** Historical data import (CSV/Excel/JSON/Parquet upload → `data_import_jobs` with
  validation report: duplicates, missing candles, timezone detection); Data export; Instrument
  master browser and mapping inspector; Cost calculator (Indian charges for a hypothetical
  trade on a date); Greeks calculator; External charting links (TradingView, GoCharting).
- **Data:** `POST /imports`, `GET /imports/{id}`, `GET /instruments`, `GET /instruments/{id}/mappings`,
  `POST /tools/cost-estimate`, `POST /tools/greeks`.
- **Phase:** 2 (import, instruments), 4 (cost calculator).

#### `/settings`
- Tabbed. Phase 1 ships the skeleton with Profile, Security and Appearance; others fill in later.
  - `/settings/profile` — name, email, timezone display preference. **Phase 1.**
  - `/settings/security` — password change, TOTP enrol, active sessions. **Phase 1.**
  - `/settings/brokers` — connect Upstox/Dhan (client id/secret entered once, encrypted at
    rest, never echoed back), daily login status and link, enable live trading toggle
    (requires TOTP). `GET/POST /brokers/accounts`, `GET /brokers/sessions`. **Phase 2.**
  - `/settings/providers` — default provider, mode, instrument groups to collect, raw tick
    flag (`COLLECT_RAW_TICKS`, shown as read-only env in v1). **Phase 2.**
  - `/settings/risk` — per-account limits: max risk per trade %, daily loss %, weekly loss %,
    max drawdown %, exposure caps, correlation cap, event block list, session window,
    sleep-hours gate. Edits locked during market hours (shown with reason). **Phase 3.**
  - `/settings/notifications` — Telegram bot token/chat id, which alerts to send. **Phase 2.**
  - `/settings/users` — users and roles (owner/trader/viewer), invite by CLI only in v1. **Phase 1 (read-only).**
  - `/settings/ai` — LLM provider selection, model, token budgets per job type, prompt
    versions in use. **Phase 5.**

---

## 4. Phase 1 shell

What "working application after Phase 1" means for the frontend. Nothing here fakes data.

1. **Layout:** App shell with collapsible grouped sidebar (all 15 items present; items whose
   phase has not shipped render a "Coming in Phase N" placeholder page, not a 404), top bar
   with market selector (NSE only), session clock driven by the real trading calendar,
   provider status pill and broker session pill.
2. **Auth:** `/login` with password and optional TOTP, silent refresh, protected routes,
   `/settings/security` and `/settings/profile`.
3. **Design tokens and components:** `tokens.css`, Tailwind config, `DataStateBadge`,
   `ModeTag`, `AiBadge`, `Money`, `Pct`, `MetricTile`, table primitives, chart wrapper
   stub (renders an empty chart with a Disconnected state).
4. **Dashboard:** All 15 panels laid out. Real data in: session clock, provider status
   (reports "No provider configured" or the actual adapter health), broker session status
   ("No broker connected"), multi-market status (NSE row). Every other tile shows an
   em-dash and a **Disconnected** or **Not available (Phase N)** badge. No zeros, no sample
   prices.
5. **Settings skeleton:** Tabs present; Brokers/Providers/Risk/Notifications/AI tabs show
   their phase placeholder.
6. **Multi-market:** NSE card read-only from the `exchanges` table.
7. **Generated API client:** `pnpm gen:api` produces types from the FastAPI OpenAPI document;
   no hand-written API types.
8. **Smoke tests:** Playwright: login, sidebar navigation to every route, dashboard renders
   with Disconnected badges.

---

## 5. Accessibility and keyboard

- All tables and forms keyboard navigable; focus rings use `--accent-cyan`.
- Colour is never the only carrier of meaning: P&L has a sign, state badges have text,
  mode tags have labels.
- Kill switch and live approvals require a typed confirmation, not just a click.
- Reduced-motion preference disables the live pulse and transitions.
