# Sachinx1911/Stock-Market-Prediction-Software — AI-MIOS v1 (owner's earlier project)

- Source: https://github.com/Sachinx1911/Stock-Market-Prediction-Software (studied commit
  `a9fe832`, 2026-07-26, "Add Phase 5 frontend + tests; v1 feature-complete")
- **Owner's own repository**, built with Claude Code before Live-Trading-Desk. Ideas and code
  may be reused freely (same owner); copying still goes through our review, tests and rules.
- Size: ~2,800 lines of Python (`app/`), Next.js 16 frontend, 21 test files (80+ tests),
  2 Alembic migrations, phase docs, CI.

## What it is

"AI-MIOS v1": an **end-of-day market analysis app for NSE**, explicitly *not* a trading
system (no broker, no orders, no intraday). Its own docs keep the scope small on purpose and
park the big vision in `docs/09_FUTURE_VISION.md`.

| Phase | What was built |
|---|---|
| 1 Data | Nifty 50 + NIFTY/BANKNIFTY seeded (53 instruments, TATAMOTORS demerger handled); 10-year daily back-fill (128,000 candles, 2016–2026); daily NSE bhavcopy ingest with delivery qty, raw CSV archive, yfinance fallback; APScheduler jobs; DB backup verified by restore |
| 2 Indicators + dashboard | Hand-rolled RSI, EMA 20/50/200, MACD, Bollinger, SuperTrend, avg volume (TradingView conventions, tested); 1.66 M indicator rows; derived states (EMA200 side, RSI zone, MACD cross…); **market breadth snapshot** (advances/declines, 52-week highs/lows, % above EMA200) back-filled for 2,471 days; screener; Next.js dashboard with 10-year charts |
| 3 News | 4 RSS feeds (Moneycontrol, ET Markets, LiveMint), dedup, **News Analyst** agent (Claude Haiku): sentiment by market impact, materiality, tags from a fixed vocabulary, batched JSON, invalid items skipped; daily AI budget guard; `/news` page and related news per stock |
| 4 Daily brief | **Brief Writer** agent at 19:00 IST: technicals vs news vs synthesis kept separate, explicit stance (direction, horizon, confidence, **invalidation condition**), mandatory disclaimer, JSON stance block; NSE holiday calendar; Telegram delivery; `/brief` page |
| 5 Accuracy loop | Every directional statement goes to `observation_log` with the reference close and confidence; a scorer grades it after its horizon (±1 % threshold, trading-day arithmetic); `/accuracy` page shows the AI's real hit-rate |

Open in its own progress file: live runs with a real Claude key, unattended week of briefs, CI.

## What we can take

| Idea | For Live-Trading-Desk / JARVIS |
|---|---|
| **Accuracy loop**: log every AI claim with reference price and confidence, score it later | JARVIS (JARVIS/KAREN modes) must not just "sound right". Log each directional statement it makes as an observation and score it; show the hit-rate on a page. Strongest idea in the repo; fits plan §2.3 "every number from a tool" and the Review protocol |
| Stance with **invalidation condition** | Every JARVIS view states when it is wrong ("view invalid below 23,800"); later usable as an alert |
| Technicals / news / synthesis kept apart | JARVIS answers label which part comes from data, which from news, which is its opinion |
| **News pipeline** (RSS → analyst → tagged, sentiment, materiality) | We have **no news at all** today. Fills "today's events" in the Market Open protocol and EDITH alerts on high-materiality news for tracked symbols. Stage 3 or 4 candidate |
| **Market breadth snapshot** (A/D, % above EMA200, 52w highs/lows) with 10 years of history | Input for our market regime module and the NIFTY 50 heatmap (design image 11) |
| Daily brief at 19:00 IST to Telegram | Our end-of-day report (Stage 3.3) and Market Close protocol |
| 10-year daily data, already validated | Can be imported through our existing NSE/data-import pipeline instead of downloading again (data lives in that project's database on the MacBook) |
| NSE holiday calendar, trading-day arithmetic, demerger handling | Check against ours; reuse the holiday file if ours lacks one |
| Fixed tag vocabulary, batched JSON, skip invalid items, daily budget guard | Same pattern as our ADR-009 boundary; confirms the approach |
| Future vision list (options snapshot, similarity search "market time machine", bull/bear debate, event memory, custom alerts, sector rotation, results calendar) | Most already in our plan; **similarity search** and **event memory** fit JARVIS memory (research note) later |

## Differences to keep in mind

- Uses the **Anthropic Claude API**; Live-Trading-Desk decided on OpenAI behind `LLMProvider`.
  Prompts and logic port across; the client does not.
- Single FastAPI app with APScheduler; ours uses separate worker (arq), collector and trader
  processes. Jobs would move to arq.
- Daily data only; we have intraday, option chains and paper trading.
- Educational disclaimer and SEBI note: keep in mind if anything is ever shown to others.

## Verdict

A finished, well-tested small sibling project. The pieces we do not have yet are **news
analysis**, **market breadth**, the **daily AI brief** and above all the **accuracy loop**
for AI statements. These are good candidates to bring into Mark 1 (news + breadth in Stage 3,
accuracy loop with JARVIS in Stage 4–5).
