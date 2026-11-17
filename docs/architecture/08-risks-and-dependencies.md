# 08 · Risks, Dependencies and Open Questions

What the project needs from outside, what can go wrong, and what we do about each. Review
this at the end of every phase and move items between sections as they are resolved.

Likelihood and impact use **L / M / H**. Risk owner is the single developer unless noted.

---

## 1. External dependencies

| Dependency | Needed by | Status | Notes |
|------------|-----------|--------|-------|
| **Upstox developer app** (API key, secret, redirect URL) | Phase 2 | To confirm | Free. Requires an Upstox trading account. Market Data Feed v3 (protobuf) for live; historical API for candles; expired-instrument endpoints for options history. Daily token expiry (ADR-012). |
| **Dhan API access** | Phase 7 | To confirm | Requires Dhan account; live data feed has a small monthly charge; 20-level depth is a separate feed. Token valid 24h. |
| **OpenAI API key** | Phase 5 | To confirm | Structured Outputs required. Budget caps enforced in code (ADR-009). Interface allows Claude/Gemini/local later. |
| **Linux VPS** (2 vCPU, 4 GB RAM, 100 GB disk, Mumbai region preferred) | Phase 2 | To confirm | Collector must run every session unattended; a laptop is not acceptable. Mumbai minimises latency to NSE and broker endpoints. |
| **Telegram bot** (bot token, chat id) | Phase 2 | Trivial | Daily login reminders, kill-switch and disconnect alerts, daily summary. |
| **Domain + TLS** | Phase 2 | To confirm | Needed for OAuth redirect URL and HTTPS to the VPS. |
| **TimescaleDB image** (`timescale/timescaledb-ha`) | Phase 1 | Available | Pin a major version; verify ARM image for local Mac development. |
| **Redis 7, MinIO** | Phase 1 | Available | Pinned in compose. |
| **NSE public downloads** (bhavcopy, holidays, F&O lot sizes, FII/DII, participant OI) | Phase 2 | Available | Formats change without notice; parsers need fixtures and alerts on failure. |
| **Historical data vendor** (GDFL / TrueData / Accelpix) | Phase 4, optional | Not decided | Only if broker history proves insufficient for the strategies being tested. Decide with data, not upfront. |
| **TA-Lib** (test dependency only) | Phase 3 | Available | Used solely to verify our Polars indicators; not a runtime dependency. |
| **Sentry** (or self-hosted GlitchTip) | Phase 10 (earlier recommended) | To confirm | Free tier sufficient. |

---

## 2. Technical risks

### 2.1 Historical intraday depth from brokers is shallow
- **L:** H · **I:** M
- Upstox and Dhan provide daily history back many years, but 1-minute history for a limited
  window and no historical ticks. Backtests on 5-minute data over several years may not be
  possible from brokers alone.
- **Mitigation:** Collector stores 1-minute candles from day one so depth grows daily
  (ADR-010). Coverage matrix is recorded per instrument × timeframe and shown in the backtest
  form; backtests on low coverage require explicit acknowledgement. Vendor purchase is a
  Phase 4 decision driven by actual gaps.

### 2.2 Expired options data is incomplete or unavailable
- **L:** H · **I:** M (H for options strategies)
- Historical option chains with OI/IV are not generally available from brokers; Upstox's
  expired-instrument endpoints cover a limited period.
- **Mitigation:** Snapshot the live chain every 5 minutes from Phase 2. Options backtests
  declare their data source and coverage. Treat vendor options history as a separate,
  justified purchase.

### 2.3 Daily token expiry breaks unattended operation
- **L:** H (certain) · **I:** M
- Both brokers require the user to complete OAuth/TOTP daily. Automation violates terms.
- **Mitigation:** ADR-012: 08:15 IST check, Telegram link, prominent UI state. Engines
  refuse to start on an expired session and show Disconnected. Operationally this is a
  30-second daily ritual; it is documented as part of the pre-market checklist.

### 2.4 Feed conflation, disconnects and clock drift
- **L:** H · **I:** M
- Broker WebSockets drop a few times per session and may conflate ticks under load. Candles
  built from a conflated feed differ from exchange candles.
- **Mitigation:** Reconnect with backoff; gap report per session; store `provider_ts` and
  `received_ts`; store LTQ and cumulative volume so conflation is detectable; nightly
  reconcile collector candles against the provider's historical candles and flag deltas.
  NTP on the VPS.

### 2.5 Backtest and paper results diverge
- **L:** M · **I:** H (undermines trust in the whole system)
- Different fill assumptions, warm-up handling or timestamp alignment between modes.
- **Mitigation:** ADR-002 one engine and one simulator; Phase 4 cross-check test comparing
  backtest on a recorded session with paper results from the same session, with a documented
  tolerance; slippage calibrated from paper fill logs.

### 2.6 Look-ahead and other backtest biases
- **L:** M · **I:** H
- Indicators computed on full arrays, candles timestamped at close, lot sizes from today
  applied to 2015, survivorship in the instrument universe.
- **Mitigation:** Event-driven evaluation with incremental indicators; candle `ts` = open
  (ADR-006); point-in-time instrument master and lot-size history (ADR-011); universe
  snapshots stored per date; a test that a peeking strategy cannot run.

### 2.7 Overfitting via AI research
- **L:** H · **I:** H
- An LLM that proposes parameter sweeps will find curves that fit the past.
- **Mitigation:** Mandatory walk-forward and out-of-sample gates before any candidate can
  reach paper; parameter count limits in the DSL validator (warn > 3, block > 6);
  neighbourhood-stability check; paper period minimum before approval; approvals are human.

### 2.8 LLM cost blow-up
- **L:** M · **I:** M
- Nightly research loops or retry storms can spend heavily.
- **Mitigation:** Per-job and per-day token budgets enforced in `packages/ai/llm`; `ai_calls`
  table with cost; dashboard spend tile; hard stop with alert when a budget is hit (ADR-009).

### 2.9 LLM output quality for Marathi and Hindi
- **L:** M · **I:** M
- Indicator names, numbers and conditions in mixed-script text may be misread.
- **Mitigation:** Structured Outputs with a strict schema; evaluation set of ≥100 descriptions
  across three languages gating prompt changes in CI; original text pinned and every AI
  change surfaced as a diff the user must accept.

### 2.10 Lightweight Charts lacks indicators and drawing tools
- **L:** H (certain) · **I:** L
- Indicators must be computed server-side or client-side and plotted as series; no drawing
  tools, no built-in option chain.
- **Mitigation:** Indicator values come from the same `packages/strategy/indicators` library
  via the API so chart and engine always agree. Drawing is out of scope for v1; external
  charting links in `/tools`.

### 2.11 Broker API changes
- **L:** M · **I:** M
- Both brokers have shipped breaking versions in the past.
- **Mitigation:** Adapter isolation (CLAUDE.md), recorded-fixture contract tests that fail
  loudly, provider version pinned in config, failover to the second provider from Phase 7.

### 2.12 Timezone and session-edge bugs
- **L:** M · **I:** M
- Pre-open auction, Muhurat sessions, half-days, DST for future markets.
- **Mitigation:** ADR-006 UTC storage; `trading_calendars` with session types; calendar unit
  tests per exchange including special sessions.

### 2.13 Secrets handling
- **L:** L · **I:** H
- Broker secrets or tokens leaking via logs, frontend bundles or repository.
- **Mitigation:** Encrypted at rest with `SECRETS_KEY`; never returned by any API after
  save; structured logger redaction list; `.env` ignored; secret-scanning in CI; frontend
  receives only session validity, never tokens.

### 2.14 Storage growth
- **L:** L (while raw ticks are off) · **I:** L
- Option-chain snapshots across many expiries can grow faster than expected.
- **Mitigation:** Timescale compression and retention; snapshot only tracked expiries;
  Phase 8 cold archive to Parquet.

---

### Finding (2026-11-17): expired-contract candles need Upstox Plus
Upstox's expired-instruments historical candle API (`/v2/expired-instruments/historical-candle/...`)
is documented as available only with an Upstox Plus subscription (error UDAPI1149). Options
backtests on past expiries therefore need either that subscription or a licensed vendor (Phase 4
decision). Live chain snapshots collected from Phase 2 onward reduce the dependency over time.

## 3. Legal and compliance risks

### 3.1 SEBI framework for retail algorithmic trading — **verify before Phase 10**
- **L:** M · **I:** H
- SEBI's 2025 framework on retail participation in algorithmic trading, implemented through
  brokers and exchanges, introduces requirements around API-based orders (for example
  registration/tagging of algos above order-rate thresholds, static IP whitelisting, broker
  approval of strategies, and treatment of self-developed algos). Exact obligations depend
  on the broker's implementation and may change.
- **Mitigation:** Before enabling live trading, obtain the current requirements from Upstox
  (and Dhan) in writing, record them in an ADR, and implement what is needed (order-rate
  limiter, static IP from the VPS, algo tagging where required). Treat this as a blocking
  item in Phase 10. This document is not legal advice; consult a professional if in doubt.

### 3.2 NSE market data licensing and redistribution
- **L:** L (personal use) · **I:** H (if the product is ever shared or sold)
- Storing broker-supplied data for personal use is normal. Redistributing it, or building a
  multi-user product on it, requires exchange data licensing.
- **Mitigation:** v1 is single-operator (ADR-014). Any move to multiple external users
  triggers a licensing review before launch. Data provenance is stored per row so the
  question "where did this come from" is always answerable.

### 3.3 Broker API terms
- **L:** L · **I:** M
- Automated login, excessive request rates or using data outside the account holder's own
  trading can breach terms.
- **Mitigation:** No login automation (ADR-012); rate-limit manager in each adapter; only
  the account holder's own data and orders.

### 3.4 Tax and cost accuracy
- **L:** M · **I:** M
- STT, stamp duty, exchange charges and SEBI fees change; wrong rates produce wrong P&L and
  wrong backtests.
- **Mitigation:** `cost_schedules` with effective dates and source URL (ADR-011); contract-
  note comparison tests on real trades once paper/live data exists.

---

## 4. Operational risks

### 4.1 Single-developer bus factor
- **L:** H (structural) · **I:** H
- **Mitigation:** This documentation set and ADRs; CLAUDE.md rules so AI assistance stays
  consistent; tests as executable specification; `docs/progress.md` kept current;
  everything reproducible from `docker compose up`.

### 4.2 Unattended collector failure
- **L:** M · **I:** M (lost data for that session)
- **Mitigation:** systemd/Compose restart policies; heartbeat alert if no tick for 60s
  during market hours; gap report every session; VPS monitoring.

### 4.3 Live trading operational errors
- **L:** M · **I:** H
- Wrong account, stale positions, double submission, kill switch untested.
- **Mitigation:** ADR-007 gates and idempotency; reconciliation blocks new orders on
  mismatch; kill-switch drill in Phase 10 and monthly thereafter; one-lot validation period;
  typed confirmations for live approval.

### 4.4 Scope creep from a 30-module specification
- **L:** H · **I:** M
- **Mitigation:** Phase exit criteria; every phase ends with a working application;
  deviations recorded as ADRs, not silently.

### 4.5 Developer discipline mirrors trader discipline
- **L:** M · **I:** M
- Changing strategy code and trading on the same day; editing risk limits during a loss.
- **Mitigation:** Market-hours edit lock on risk limits and strategy activation changes;
  release cadence documented (code on Friday, paper Monday, live the following week).

---

## 5. Risk register summary

| # | Risk | L | I | Phase to address |
|---|------|---|---|------------------|
| 2.1 | Shallow intraday history | H | M | 2, 4 |
| 2.2 | Expired options data | H | M | 2, 4 |
| 2.3 | Daily token expiry | H | M | 2 |
| 2.4 | Feed conflation/disconnects | H | M | 2 |
| 2.5 | Backtest/paper divergence | M | H | 3, 4 |
| 2.6 | Backtest biases | M | H | 4 |
| 2.7 | AI overfitting | H | H | 5, 6 |
| 2.8 | LLM cost | M | M | 5 |
| 2.9 | Multilingual NL quality | M | M | 5 |
| 2.10 | Charting limits | H | L | 2 |
| 2.11 | Broker API changes | M | M | 2, 7 |
| 2.12 | Timezone/session edges | M | M | 1 |
| 2.13 | Secrets | L | H | 1 |
| 2.14 | Storage growth | L | L | 8 |
| 3.1 | SEBI retail algo framework | M | H | 10 (blocking) |
| 3.2 | Data licensing | L | H | before any multi-user use |
| 3.3 | Broker terms | L | M | 2 |
| 3.4 | Cost accuracy | M | M | 3 |
| 4.1 | Bus factor | H | H | ongoing |
| 4.2 | Collector failure | M | M | 2 |
| 4.3 | Live operational errors | M | H | 10 |
| 4.4 | Scope creep | H | M | ongoing |
| 4.5 | Discipline | M | M | 3 |

---

## 6. Open questions for the product owner

Answers unblock specific phases; none block Phase 1.

1. **UI reference.** The master prompt mentions an "existing UI reference". The repository is
   empty. Is there a Figma file, screenshots or a link? If not, the design system in
   `06-ui-page-map.md` is built from the written direction alone.
2. **Upstox developer app.** Is an Upstox account with API access already set up (API key,
   secret, redirect URL)? Needed at the start of Phase 2.
3. **Dhan account and API subscription.** Available now, or to be arranged before Phase 7?
4. **OpenAI key and monthly budget.** What monthly spend is acceptable for research jobs?
   The budget becomes a hard limit in configuration.
5. **VPS.** Any existing provider preference? Mumbai region recommended. Who holds root access?
6. **Domain name** for the OAuth redirect and HTTPS.
7. **Historical data budget.** Is a paid vendor (GDFL/TrueData/Accelpix, roughly a few
   thousand rupees per month) acceptable if Phase 4 shows broker history is insufficient?
8. **Instrument scope for the collector.** Confirm: NIFTY and BANKNIFTY (spot, current and
   next-month futures, weekly ATM ±5 strikes), India VIX, and a list of up to 30 liquid
   NIFTY 50 stocks. Changes later are config, but the earlier the list is right, the more
   history accumulates.
9. **Raw ticks.** Keep `COLLECT_RAW_TICKS=false` (agreed in discussion) or enable it for
   index futures only from day one? Cost is roughly 10–20 MB per instrument per day.
10. **Paper account defaults.** Initial capital ₹1,00,000 confirmed; default brokerage plan
    to model (flat per-order discount broker is assumed).
11. **Notification channel.** Telegram confirmed, or is another channel preferred?
12. **Live trading timeline.** Live is scheduled for Phase 10 after a four-week one-lot
    validation. Any reason to bring parts earlier (not recommended)?
