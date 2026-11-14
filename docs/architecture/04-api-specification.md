# 04 · API Specification (v1)

Backend: FastAPI, all routes under `/api/v1`. WebSocket channels under `/ws`. OpenAPI is
served at `/api/v1/openapi.json` and is the source for the generated TypeScript client
(`pnpm gen:api`). This document is the human contract; the OpenAPI file is the machine one.
When they disagree, fix the code so OpenAPI matches this document, or amend this document
with an ADR.

**Hard rule (ADR-009):** no endpoint accepts an order from an LLM, an AI job, or any
server-side agent. Order endpoints are called only by an authenticated human session or by
the deterministic strategy engine bound to a user-signed activation. AI routes return
proposals and reports only.

---

## 1. Conventions

### 1.1 Authentication
- `Authorization: Bearer <access_jwt>`; access tokens live 15 minutes, refresh tokens rotate
  (`POST /auth/refresh`). Refresh token is an `HttpOnly` cookie for the web client.
- Roles: `owner`, `trader`, `viewer` (ADR-014). Endpoints list the minimum role.
- Mutating `live/*`, `risk/limits`, `strategies/*/approvals`, `strategies/*/activations`
  require a fresh re-auth (`X-Reauth-Token`, obtained via `POST /auth/reauth` within the
  last 5 minutes) — "step-up" confirmation.

### 1.2 Error envelope
```json
{ "error": { "code": "RISK_REJECTED", "message": "Max daily loss reached", "details": {"gate": 4}, "request_id": "req_01J..." } }
```
HTTP codes: 400 validation, 401/403 auth, 404, 409 conflict/idempotency replay with
different body, 422 domain rule (e.g. DSL invalid), 423 locked (kill switch / market closed
/ edit lock during market hours), 429 rate limit, 503 provider unavailable.

### 1.3 Pagination
Cursor-based: `?limit=50&cursor=<opaque>`; response `{ "items": [...], "next_cursor": "..." | null }`.
Time-range endpoints use `from`/`to` as ISO-8601 UTC.

### 1.4 Idempotency
All `POST` on `/paper/.../orders` and `/live/.../orders` require `Idempotency-Key` (UUID).
Same key + same body → same response (replayed, `Idempotent-Replayed: true`); same key +
different body → 409. Keys are stored 7 days. Engine-generated orders use
`strategy_version_id + signal_id` as the key (ADR-007).

### 1.5 Market-data freshness and provenance
Every quote, candle, chain and derived value carries:
```json
{ "source": { "provider": "upstox", "provider_ts": "2026-11-14T04:15:00.120Z", "received_ts": "..." },
  "freshness": "live" | "delayed" | "disconnected" | "historical" | "demo" }
```
The UI must render `freshness`. `demo` is only emitted when `APP_DEMO_MODE=true` and is
never mixed with `live` in one response.

### 1.6 Time
All timestamps UTC ISO-8601 (ADR-006). Candle `ts` = bar open time. Clients pass
`market` to get the exchange timezone from `/exchanges`.

### 1.7 Common ids
Prefixed ULIDs: `usr_`, `str_`, `sv_` (strategy version), `bt_`, `ord_`, `pos_`, `trd_`,
`job_`, `rev_`, `rec_`.

---

## 2. Auth & Users

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/auth/login` | – | email+password (+`totp` if enabled) → access token, refresh cookie |
| POST | `/auth/refresh` | – | rotate refresh, new access |
| POST | `/auth/logout` | any | revoke refresh |
| POST | `/auth/reauth` | any | password/TOTP → `X-Reauth-Token` (5 min) |
| GET | `/users/me` | any | profile, roles, preferences (timezone, default market) |
| PATCH | `/users/me` | any | preferences |
| GET | `/users` · POST `/users` · PATCH `/users/{id}` | owner | manage users and roles (no public signup) |
| POST | `/users/me/totp/enable` · `/disable` | any | TOTP setup |

```json
POST /auth/login  { "email": "a@b.c", "password": "...", "totp": "123456" }
→ { "access_token": "...", "expires_in": 900, "user": { "id": "usr_...", "roles": ["owner"] } }
```

## 3. Exchanges & Providers

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/exchanges` | any | NSE, BSE… with timezone, session rules, currency |
| GET | `/exchanges/{code}/calendar?from&to` | any | trading days, holidays, special sessions |
| GET | `/providers` | any | configured data providers, capabilities, entitlements |
| GET | `/providers/{id}/health` | any | connection state, feed latency p50/p95, last tick ts, reconnects today |
| GET | `/providers/mode` | any | `{ "mode": "single"|"comparison"|"failover", "primary": "upstox", "secondary": "dhan" }` |
| PUT | `/providers/mode` | owner | set mode and primary/secondary |
| POST | `/providers/{id}/switch` | owner | make this provider primary (controlled failover) |
| GET | `/providers/comparison?instrument&from&to` | trader | price/timestamp/volume/missing-candle diffs between providers (Module 15) |

## 4. Brokers & Sessions (ADR-012)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/brokers/accounts` | trader | linked broker accounts, masked client ids |
| POST | `/brokers/accounts` | owner | add account (api key/secret stored encrypted server-side) |
| DELETE | `/brokers/accounts/{id}` | owner | remove |
| GET | `/brokers/accounts/{id}/login-url` | trader | OAuth URL for today's login |
| GET | `/brokers/callback/{broker}` | – | OAuth redirect target; exchanges code for token, stores in `broker_sessions` |
| GET | `/brokers/accounts/{id}/session` | trader | `{ "status": "valid"|"expired"|"missing", "expires_at": "...", "scopes": [...] }` |
| GET | `/brokers/accounts/{id}/margins` | trader | available/used margin from broker |

Secrets never appear in any response.

## 5. Instruments

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/instruments?q=NIFTY&exchange=NSE&segment=FO&type=OPT` | any | search; returns canonical instrument with `isin`, `exchange_token`, lot size, tick size |
| GET | `/instruments/{id}` | any | detail + current contract spec + provider mappings |
| GET | `/instruments/{id}/history` | any | lot/tick size and symbol history (point-in-time) |
| GET | `/instruments/{id}/corporate-actions` | any | splits, bonus, dividends |
| GET | `/instruments/{underlying}/contracts?expiry&kind=FUT|OPT` | any | derivative contracts |
| GET | `/instruments/{underlying}/option-chain?expiry` | any | chain with OI, ΔOI, IV, greeks, LTP, bid/ask per strike + `freshness` |
| GET | `/instruments/{underlying}/option-chain/snapshots?expiry&from&to&step=5m` | trader | stored snapshots (ADR-010) |
| POST | `/instruments/master/refresh` | owner | enqueue instrument-master import from primary provider → `job_` |

## 6. Market Data

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/market-data/candles?instrument_id&timeframe=1m|5m|15m|30m|1h|1d|1w|1M&from&to&adjusted=true&provider=` | any | canonical candles; `adjusted` applies corporate actions as a view |
| GET | `/market-data/quotes?instrument_ids=a,b,c` | any | last quote per instrument with depth (levels available), `freshness` |
| GET | `/market-data/vix?from&to` | any | India VIX series |
| GET | `/market-data/regime?market=NSE&date=` | any | current regime record (trend/range, vol bucket, inputs) |
| WS | `/ws/market` | any | live subscribe (see §17) |

```json
GET /market-data/candles?instrument_id=ins_nifty&timeframe=5m&from=...&to=...
→ { "instrument_id": "ins_nifty", "timeframe": "5m", "adjusted": false,
    "candles": [{ "ts": "2026-11-14T03:45:00Z", "o": 24010.5, "h": 24030.0, "l": 24001.2, "c": 24022.0, "v": 123400, "oi": 0 }],
    "source": { "provider": "upstox", ... }, "freshness": "historical" }
```

## 7. Historical Data Management

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/historical/backfill` | owner | `{ instrument_ids, timeframe, from, to, provider }` → `job_` |
| POST | `/historical/imports` | owner | multipart upload CSV/XLSX/JSON/Parquet + mapping spec → `job_` (raw file archived to MinIO with checksum) |
| GET | `/historical/imports/{job_id}` | trader | status, rows read/accepted/rejected, manifest |
| GET | `/historical/coverage?instrument_id&timeframe` | any | per-provider coverage ranges and gap counts |
| POST | `/historical/quality-checks` | trader | run duplicate/missing-candle/outlier checks → `job_` |
| GET | `/historical/quality-checks/{id}` | any | findings |
| POST | `/historical/exports` | trader | `{ instrument_ids, timeframe, from, to, format: "csv"|"parquet" }` → `job_`, download URL when done |

## 8. Strategies

Strategy = container; **strategy version** = immutable DSL document with a status
lifecycle: `draft → validated → backtested → paper_validated → approved_live → retired`.
Only `draft` is editable. Any edit of a non-draft creates a new version.

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/strategies?category&status&origin=user|ai` | any | library listing |
| POST | `/strategies` | trader | create container + first draft version `{ name, category, dsl }` |
| GET | `/strategies/{id}` | any | container, latest version summary, performance history |
| PATCH | `/strategies/{id}` | trader | rename, category, tags |
| DELETE | `/strategies/{id}` | owner | soft delete (never if an activation exists) |
| GET | `/strategies/{id}/versions` | any | version list with status, created_by (user/ai job), parent_version |
| POST | `/strategies/{id}/versions` | trader | new draft `{ dsl, parent_version_id, change_note }` |
| GET | `/strategies/{id}/versions/{vid}` | any | full DSL + validation report + linked backtests |
| PUT | `/strategies/{id}/versions/{vid}` | trader | update DSL — **only while `draft`**, else 423 |
| POST | `/strategies/{id}/versions/{vid}/validate` | trader | DSL validation → report, status `validated` |
| POST | `/strategies/{id}/clone` | trader | copy to new container |
| POST | `/strategies/compare` | any | `{ version_ids, backtest_config }` → `job_` (identical data/costs) |
| POST | `/strategies/generate` | trader | **NL builder** (below) |
| POST | `/strategies/generate/{draft_id}/answer` | trader | answer clarification questions → updated draft |
| POST | `/strategies/{id}/versions/{vid}/approvals` | owner + reauth | `{ target: "paper"|"live", note }` → status change; records approver, time, evidence ids |
| GET | `/strategies/approvals/queue` | owner | pending candidates (AI and user) with evidence summary |
| POST | `/strategies/{id}/versions/{vid}/activations` | owner + reauth | `{ mode: "paper"|"live", account_id, instruments, risk_profile_id }` — live requires `approved_live` |
| DELETE | `/activations/{id}` | trader | deactivate (always allowed, no reauth) |
| GET | `/activations?mode&status` | any | running strategies |

### 8.1 Natural-language builder — `POST /strategies/generate`
Request (exactly as the master prompt):
```json
{ "language": "mr", "market": "NSE", "instrument": "NIFTY", "timeframe": "5m",
  "description": "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा." }
```
Response:
```json
{ "draft_id": "nld_01J...", "status": "draft",
  "strategy_name": "NIFTY EMA Momentum", "market": "NSE", "instrument": "NIFTY", "timeframe": "5m",
  "entry_conditions": [
    { "indicator": "EMA", "period": 9, "condition": "crosses_above", "target": { "indicator": "EMA", "period": 21 } },
    { "indicator": "RSI", "condition": "greater_than", "value": 55 } ],
  "exit_conditions": [],
  "risk_management": { "stop_loss": null, "target": null },
  "missing_information": ["Exit condition", "Position sizing"],
  "clarification_questions": [
    { "id": "q1", "field": "exit_conditions", "question_mr": "Exit कधी करायचा? (उदा. EMA 9 EMA 21 खाली आल्यावर, किंवा target/stop वर)", "question_en": "When should the position exit?" },
    { "id": "q2", "field": "position_sizing", "question_mr": "किती lots किंवा किती risk प्रति trade?", "question_en": "How many lots or what risk per trade?" } ],
  "dsl": { "...": "full Strategy DSL v1 document, partially filled, see 05-strategy-dsl.md" },
  "original_text": "EMA 9 ने ...", "detected_language": "mr",
  "ai_call_id": "aic_01J..." }
```
Rules: the response is validated against the DSL schema before leaving the server; fields
the user did not specify are `null` and listed in `missing_information`; the server never
fills defaults silently. `POST /strategies` with `dsl` from the draft creates the version.

## 9. Backtesting

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/backtests` | trader | create job (below) → `{ "job_id": "bt_...", "status": "queued" }` |
| GET | `/backtests?strategy_version_id&status` | any | list |
| GET | `/backtests/{id}` | any | status, progress %, config, data provenance (provider, snapshot hash), seed |
| GET | `/backtests/{id}/results` | any | metrics, equity curve (downsampled), drawdown series, monthly table |
| GET | `/backtests/{id}/trades?cursor` | any | trade list with entry/exit reason, costs breakdown, MAE/MFE |
| GET | `/backtests/{id}/report` | any | AI-free deterministic report (markdown) |
| DELETE | `/backtests/{id}` | trader | cancel if running |
| POST | `/backtests/optimizations` | trader | `{ strategy_version_id, param_grid | random:{n}, objective, constraints, data }` → job |
| GET | `/backtests/optimizations/{id}` | any | results table, sensitivity heatmap data, overfitting flags (parameter plateau, IS/OOS ratio) |
| POST | `/backtests/walk-forward` | trader | `{ strategy_version_id, windows: {train_days, test_days, step_days}, param_grid }` → job |
| GET | `/backtests/walk-forward/{id}` | any | per-window chosen params + OOS metrics, stitched OOS equity |
| POST | `/backtests/compare` | any | alias of `/strategies/compare` |

```json
POST /backtests
{ "strategy_version_id": "sv_...", "instrument_ids": ["ins_nifty_fut_cm"], "timeframe": "5m",
  "from": "2019-01-01", "to": "2025-12-31", "initial_capital": 1000000,
  "costs": { "schedule": "nse_fo_default", "slippage_model": "spread_plus_bps", "slippage_bps": 2 },
  "fill_model": "next_bar_open" | "bar_bid_ask" | "tick",
  "data": { "provider": "upstox", "adjusted": true }, "seed": 42,
  "out_of_sample_from": "2024-07-01" }
```
Metrics returned: total_return, cagr, win_rate, profit_factor, max_drawdown, max_dd_duration,
sharpe, sortino, calmar, expectancy, avg_win, avg_loss, total_trades, exposure_time,
max_consecutive_losses, costs_total; each also for the OOS segment.

## 10. Historical Replay

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/replay/sessions` | trader | `{ instrument_ids, date, timeframe, strategy_version_id?, speed }` → `{ session_id }` |
| GET | `/replay/sessions/{id}` | any | state, cursor ts, virtual positions |
| DELETE | `/replay/sessions/{id}` | trader | end |
| WS | `/ws/replay/{session_id}` | trader | control + stream (§17) |

## 11. Paper Trading (ADR-008)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/paper/accounts` · POST | trader | accounts; default capital ₹1,00,000, editable `{ name, initial_capital, cost_schedule, slippage_model }` |
| POST | `/paper/accounts/{id}/reset` | trader | reset capital, archive history |
| GET | `/paper/accounts/{id}` | any | capital, available, used margin (simulated), realized/unrealized P&L |
| POST | `/paper/accounts/{id}/orders` | trader | manual paper order, `Idempotency-Key` required |
| GET | `/paper/accounts/{id}/orders?status&from&to` | any | order book with fill details (bid/ask at fill, slippage, charges) |
| PATCH | `/paper/accounts/{id}/orders/{oid}` | trader | modify qty/price (if open) |
| DELETE | `/paper/accounts/{id}/orders/{oid}` | trader | cancel |
| GET | `/paper/accounts/{id}/positions` | any | open positions, MTM |
| POST | `/paper/accounts/{id}/positions/{pid}/close` | trader | square off |
| GET | `/paper/accounts/{id}/trades` | any | closed round-trips |
| GET | `/paper/accounts/{id}/performance?group_by=strategy|instrument|day` | any | aggregates |

```json
POST /paper/accounts/pa_1/orders   (Idempotency-Key: 9f1c...)
{ "instrument_id": "ins_nifty_fut_cm", "side": "BUY", "qty": 25, "order_type": "LIMIT", "price": 24010,
  "product": "INTRADAY", "stop_loss": { "trigger": 23960 }, "target": { "price": 24110 }, "tag": "manual" }
→ 201 { "order_id": "ord_...", "status": "OPEN", "simulated": true }
```

## 12. Live Trading (ADR-007)

All mutating routes require role `owner` or `trader` **and** `X-Reauth-Token`. Every
request and refusal is written to `order_events` and `audit_logs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/live/accounts` | broker-linked live accounts with session status, margins |
| POST | `/live/accounts/{id}/orders` | manual live order; `Idempotency-Key` required; passes the five gates |
| GET | `/live/accounts/{id}/orders` · GET `/orders/{oid}` | broker order ids, state history (from broker callbacks only) |
| PATCH | `/live/accounts/{id}/orders/{oid}` | modify via broker |
| DELETE | `/live/accounts/{id}/orders/{oid}` | cancel via broker |
| GET | `/live/accounts/{id}/positions` | from broker + local view, with `reconciled: bool` |
| POST | `/live/accounts/{id}/positions/{pid}/close` | square off (gates 2,5 apply; gates 1,3,4 bypassed for *reducing* risk) |
| POST | `/live/accounts/{id}/reconcile` | pull broker orders/positions, diff, write `reconciliation_runs`; mismatches set `trading_halted=true` until acknowledged |
| GET | `/live/accounts/{id}/reconciliation` | last runs and open mismatches |
| GET | `/live/kill-switch` | `{ global: bool, accounts: {...}, strategies: {...}, set_by, reason, at }` |
| POST | `/live/kill-switch` | `{ scope: "global"|"account"|"strategy", id?, reason }` — **engage**: no reauth required, any trader, from any device; cancels open orders and (if `flatten: true`) squares off |
| DELETE | `/live/kill-switch` | **disengage**: owner + reauth, not within market hours of the same day unless `force_ack` with reason |

### 12.1 The five gates (order submission)
Evaluated in order by `submit_live_order`; the first failure returns 423/422 with `details.gate`:

| # | Gate | Error code |
|---|---|---|
| 1 | Strategy version `approved_live` and activation signed by user (manual orders: user session is the signature) | `NOT_APPROVED` |
| 2 | Broker session valid for this account | `BROKER_SESSION_INVALID` |
| 3 | Risk engine `ALLOW` (size, per-trade risk, exposure, correlation, event block, session window, freeze qty) | `RISK_REJECTED` |
| 4 | Daily and weekly loss limits not breached | `LOSS_LIMIT_REACHED` |
| 5 | Kill switch off at every scope | `KILL_SWITCH_ENGAGED` |

### 12.2 Idempotency rule
Key = client `Idempotency-Key` (manual) or `sha256(strategy_version_id:signal_id)` (engine).
Stored in `live_orders.idempotency_key` with a unique index. Replay returns the original
order; the broker is never called twice for one key. Broker-side duplicate detection
(`order_tag`) is also set as defence in depth.

Order status is only ever advanced by broker callback/polling or reconciliation; the API
never reports `COMPLETE` on its own assumption.

## 13. Risk

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/risk/profiles` · POST · PATCH `/risk/profiles/{id}` | owner + reauth | named limit sets: max_risk_per_trade_pct, max_daily_loss, max_weekly_loss, max_drawdown_pct, max_open_positions, max_exposure, correlation_cap, event_block, session_window, auto_square_off_time; **PATCH returns 423 during market hours** |
| GET | `/risk/accounts/{id}/status` | any | today's used loss %, open risk, exposure, limits remaining, violations |
| POST | `/risk/check` | trader | dry-run an order through the risk engine → `{ decision: "ALLOW"|"REJECT"|"REDUCE", suggested_qty, reasons[] }` |
| GET | `/risk/violations?from&to` | any | rule breaches and blocks |

## 14. Portfolio, Analytics, Journal

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/portfolio?mode=paper|live&account_id` | any | capital, holdings, positions, margin, exposure, P&L |
| GET | `/portfolio/snapshots?from&to` | any | daily snapshots |
| GET | `/analytics/performance?mode&period=daily|weekly|monthly&group_by=strategy|instrument` | any | returns, expectancy, win rate, drawdown |
| GET | `/analytics/risk-report?mode&from&to` | any | exposure history, VaR-lite, correlation matrix of active strategies |
| GET | `/journal/trades?mode&strategy_version_id&from&to` | any | trade with regime, reasons, costs, slippage, AI review, notes, rule_compliant flag |
| PATCH | `/journal/trades/{id}` | trader | user notes, tags, mood score (1–5), answers to the 3 review questions |
| GET | `/journal/daily?date` | any | day entry: checklist, mood scores, violations, summary |
| PUT | `/journal/daily/{date}/checklist` | trader | pre-market checklist (engine start requires all items true) |

## 15. AI (ADR-009)

All responses include `ai_call_id`, `model`, `prompt_version`, `evidence` (ids of trades,
backtests, candles used) and `cost_usd`. Nothing here mutates orders, activations or limits.

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/ai/morning-brief?date&market` | any | regime, levels, bias, events, strategy on/off suggestions (suggestions only; deterministic regime shown alongside) |
| POST | `/ai/morning-brief/run` | trader | regenerate → job |
| GET | `/ai/trade-reviews?trade_id|strategy_version_id` | any | per-trade reviews |
| POST | `/ai/trade-reviews/run` | trader | `{ trade_ids }` → job |
| GET | `/ai/research/jobs` · POST | trader | `{ hypothesis, universe, timeframe, budget_tokens, max_backtests }` → job; produces `draft` candidate versions only |
| GET | `/ai/research/jobs/{id}` | any | status, report, candidate version ids, backtests run, tokens used |
| GET | `/ai/recommendations?status=pending|accepted|rejected` | any | improvement hypotheses with linked candidate version + evidence |
| POST | `/ai/recommendations/{id}/accept` | owner | moves candidate into the normal approval pipeline (still needs backtest/paper/approval) |
| POST | `/ai/recommendations/{id}/reject` | trader | with reason (fed back as evaluation data) |
| GET | `/ai/audit-findings?from&to` | owner | nightly auditor output |
| GET | `/ai/usage?from&to` | owner | tokens and cost per agent/job type |
| GET | `/ai/providers` · PUT `/ai/providers/active` | owner | OpenAI/Claude/Gemini/local — interface swap |

## 16. Admin & System

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/admin/health` | – | liveness; `{ db, redis, minio, providers[], worker_queue_depth }` |
| GET | `/admin/status` | any | market session state, active provider mode, collector status, kill switch, engine states |
| GET | `/admin/audit-logs?actor&action&from&to` | owner | every mutating action and every gate decision |
| GET | `/admin/jobs?type&status` | trader | arq jobs (backtest, import, ai, scheduled) |
| GET | `/admin/jobs/{id}` · DELETE | trader | detail / cancel |
| GET | `/admin/env` | owner | non-secret config echo (demo mode, feature flags) |
| GET | `/admin/backups` | owner | last backup/restore-test timestamps |

## 17. WebSocket channels

Connect with `?token=<access_jwt>`; server closes on expiry (client refreshes and reconnects).
Messages are JSON `{ "type": "...", "data": {...}, "ts": "..." }`. Server sends
`{ "type": "heartbeat" }` every 5 s; missing 3 → client shows `Disconnected`.

### `/ws/market`
Client: `{ "type": "subscribe", "quotes": ["ins_a","ins_b"], "candles": [{"instrument_id":"ins_a","timeframe":"1m"}], "chain": {"underlying":"ins_nifty","expiry":"2026-11-20"} }`,
`{ "type": "unsubscribe", ... }`.
Server: `quote` (ltp, bid/ask levels, volume, oi, `source`, `freshness`), `candle`
(`closed: bool`, open bars flagged so no strategy acts on them), `chain_update`,
`provider_status` (`connected|reconnecting|disconnected`, latency).

### `/ws/orders`
Server: `order_update` (paper and live, with `mode` field), `position_update`,
`fill`, `gate_refusal` (gate number, reason), `kill_switch` state changes,
`risk_status` (used daily loss %, open risk).

### `/ws/jobs`
Client: `{ "type": "watch", "job_ids": [...] }`. Server: `progress` (pct, stage, eta),
`completed`, `failed` (error code, message).

### `/ws/replay/{session_id}`
Client: `play`, `pause`, `set_speed` `{ "x": 1|2|5|10|60 }`, `step` `{ "bars": 1|-1 }`,
`seek` `{ "ts" }`. Server: `candle`, `signal`, `order_update` (virtual), `state`.

---

## 18. Rate limits
Per user: 600 req/min REST, 10 concurrent WS. Order endpoints: 60/min, and the risk engine
enforces a per-strategy order throttle. 429 includes `Retry-After`.

## 19. Versioning
Breaking changes → `/api/v2` alongside `/api/v1` for at least one release. Additive changes
are allowed in v1. Every response carries `X-API-Version`.
