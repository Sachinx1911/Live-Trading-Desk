# MASTER DEVELOPMENT PROMPT

## AI-POWERED MULTI-MARKET ALGORITHMIC TRADING PLATFORM

> This is the original master prompt supplied by the product owner (2026-11-14).
> It is preserved verbatim as the source of requirements. Deviations from it are
> recorded as Architecture Decision Records in `docs/adr/`.

---

### 1. YOUR ROLE

Act as a Principal Software Architect, Senior Quantitative Developer, AI Engineer, Algorithmic Trading Specialist, Database Architect, and Professional UI/UX Designer.

Your task is to architect and develop a complete, professional, modular, scalable AI-powered Algorithmic Trading Platform.

This is a long-term software product, not a simple trading dashboard or a basic stock market application.

You must approach this project as an institutional-grade quantitative trading platform, while keeping the architecture maintainable and practical for independent development.

Do not create a simple demo application and call it complete.

Build the platform in properly tested, independently maintainable modules.

### 2. PRODUCT VISION

Build an AI-powered Multi-Market Trading Platform that allows users to:

1. Analyze live financial markets.
2. Scan stocks and identify trading opportunities.
3. Create their own trading strategies.
4. Describe strategies in natural language.
5. Allow AI to independently research and generate strategies.
6. Backtest strategies using historical market data.
7. Perform real-time Paper Trading using virtual capital.
8. Execute real trades through broker APIs after explicit user approval.
9. Analyze every completed trade using AI.
10. Recommend improvements to trading strategies.
11. Compare multiple market data providers.
12. Eventually operate using our own independent market data infrastructure.

The platform must support future expansion into multiple exchanges and international markets.

**Core Philosophy**

* No vendor lock-in.
* Modular architecture.
* Provider-independent trading engine.
* Reproducible backtesting.
* Reliable historical data.
* AI-assisted research.
* User-controlled live execution.
* Strong risk management.
* Full auditability.

### 3. FINALIZED BUSINESS AND TECHNICAL DECISIONS

These decisions are already approved. Do not change them without a strong technical reason.

**Initial Market:** NSE India. Required segments: Equity Stocks, Indices, Futures, Options.

**Initial Data Provider:** Upstox API. **Second Data Provider:** Dhan API.

**Future Providers:** The architecture must support additional data providers without changing the core trading engine.

**Initial AI Provider:** OpenAI API. However, create an interchangeable AI provider interface so Claude, Gemini, and Local LLMs can be integrated later.

**Historical Data:** Target: All legally obtainable historical data from 2010 onwards.

**Data Granularity:** Tick Data (wherever licensed and available), 1 Second (wherever available), 1 Minute, 5 Minute, 15 Minute, 30 Minute, 1 Hour, Daily, Weekly, Monthly.

Do not assume every historical timeframe or tick record is available from every provider.

**Storage Strategy:** Initially use third-party market data APIs. Develop our own complete independent market data infrastructure in a later development phase. However, design normalized data storage and provider-independent interfaces from the beginning.

**Future Markets:** NSE, BSE, MCX, US Stock Markets, Global Indices, Forex, Crypto. These must be supported through an extensible exchange architecture, subject to legal access and licensed data availability.

### 4. COMPLETE MODULE ARCHITECTURE

Divide the platform into six major departments.

#### DEPARTMENT A: AI AND INTELLIGENCE

**Module 1: AI Trading Agent** — Analyze market conditions, identify trading opportunities, analyze technical indicators, evaluate risk, generate trade setups, explain its trading decisions, recommend whether to trade or stay out of the market.

**Module 2: AI Market Analysis** — Technical Analysis, Price Action, Trend Analysis, Volume Analysis, Volatility Analysis, Support and Resistance, Market Structure, Momentum Analysis.

**Module 3: News and Sentiment Analysis** — Analyze financial news, market events, and relevant sentiment. Maintain timestamps and source references.

**Module 4: AI Strategy Research** — AI must independently: research historical market behavior, explore trading hypotheses, generate new trading strategy candidates, test alternative parameters, identify weaknesses, suggest improvements, submit promising candidates for backtesting. AI research must not directly activate live trading strategies.

**Module 5: AI Learning Engine** — After every completed trade, analyze: entry quality, exit quality, stop-loss performance, target performance, market regime, execution slippage, trade duration, strategy performance, risk and reward, winning and losing trade patterns. Generate improvement recommendations. AI must create a new strategy version when proposing modifications. It must never silently modify an approved live strategy. All improvements must pass backtesting, out-of-sample validation, paper trading, and user approval.

**Module 6: Market Regime Detection** — Identify: Trending, Sideways, Bullish, Bearish, High Volatility, Low Volatility. Allow strategies to use market regime filters.

#### DEPARTMENT B: STRATEGY INTELLIGENCE

**Module 7: Dual Strategy Creation System** — MODE A: AI Autonomous Strategy Generation (identify patterns, generate hypotheses, create structured strategy rules, perform backtesting, optimize parameters, evaluate risk, generate research reports). MODE B: User-Created Strategies via Natural Language, Visual Strategy Builder, Python Strategy Editor. Both modes must use the same standardized Strategy Engine.

**Module 8: Natural Language Strategy Builder** — High priority. The user must be able to describe a strategy in Marathi, Hindi, English. AI must: understand the language, extract conditions, identify indicators, define entry/exit/stop-loss/target rules, identify missing information, ask clarification questions, generate structured strategy JSON, validate the rules, show a complete preview, allow edit and confirm. Never silently change the user's original conditions. Never execute arbitrary AI-generated Python code. Use a safe, predefined strategy DSL or validated JSON specification.

**Module 9: Visual Strategy Builder** — Selecting indicators, creating conditions, AND/OR combination, entry/exit rules, stop loss and target, position sizing.

**Module 10: Strategy Library and Version Control** — AI-generated and user-created strategies, categories, versions, cloning, comparison, performance history, activation status.

#### DEPARTMENT C: MARKET DATA INFRASTRUCTURE

**Module 11: Multi-Provider Manager** — Provider Adapters, Common Market Data Interface, Authentication Manager, API Rate Limit Manager, WebSocket Manager, Connection Monitoring, Provider Health Checks, Error Handling, Provider Switching. Three operating modes: Single Provider, Comparison, Controlled Failover. Use a canonical internal market data format. The core trading system must never directly depend on provider-specific API response formats.

**Module 12: Live Market Data** — Live stock prices, index values, futures, options, bid/ask, market depth, volume, open interest, WebSocket streaming.

**Module 13: Historical Data Manager** — Historical Data API, CSV/Excel/JSON/Parquet import, bulk import, validation, duplicate detection, missing candle detection, export.

**Module 14: Options and Derivatives Data** — Options chain, CE/PE, strike, expiry, OI, change in OI, volume, IV, Greeks (where available or calculated), futures contracts, contract specifications. Expired options data must use an authorized API subscription or licensed source.

**Module 15: Data Quality and Provider Comparison** — Compare Upstox and Dhan: price, timestamp, missing candles, duplicates, volume, latency, historical coverage, options accuracy, feed reliability. Do not assume differences automatically indicate errors. Normalize exchange timestamps, instrument mapping, feed types, and entitlements before comparison.

#### DEPARTMENT D: TRADING AND EXECUTION

**Module 16: Trading Engine** — Buy, Sell, Entry, Exit, Position Management, Trade Monitoring, Strategy Execution.

**Module 17: Paper Trading Engine** — Critical. Real-time paper trading using live data and virtual capital (initial ₹1,00,000, configurable). Simulate market/limit/stop-loss/target orders, partial fills, bid/ask spread, slippage, brokerage, taxes and charges, position tracking, realized and unrealized P&L. Realistic order simulation rather than last traded prices.

**Module 18: Live Trading Engine** — Order placement, modification, cancellation, position monitoring, execution reconciliation. CRITICAL SAFETY RULE: No AI-generated or user-created strategy may enter live trading without explicit user approval. Live trading requires: approved strategy version, broker authorization, risk validation, user confirmation, configured daily loss limits, emergency kill switch.

**Module 19: Order Management System** — Complete order lifecycle and execution records.

**Module 20: Risk Management Engine** — Position sizing, max risk per trade, max daily loss, max drawdown, exposure limits, portfolio risk, correlation risk, stop-loss enforcement, emergency trading shutdown.

#### DEPARTMENT E: BACKTESTING AND RESEARCH

**Module 21: Backtesting Engine** — Historical OHLCV, tick-level simulation when available, multiple instruments and timeframes, intraday/swing/futures/options strategies. Realistic brokerage, STT, exchange charges, GST, stamp duty, slippage, spread, execution delays. Calculate: total return, win rate, profit factor, max drawdown, Sharpe, Sortino, average profit/loss, expectancy, total trades, equity curve. Prevent look-ahead bias, survivorship bias, data leakage, unrealistic fills. Point-in-time data and reproducible backtesting.

**Module 22: Historical Replay Engine** — Play, pause, speed, step forward/backward, strategy execution.

**Module 23: Strategy Optimization** — Parameter optimization, walk-forward, out-of-sample, sensitivity analysis, overfitting detection.

**Module 24: Strategy Comparison** — Identical data, costs and assumptions.

#### DEPARTMENT F: PORTFOLIO AND ADMINISTRATION

**Module 25: Portfolio Manager** — Capital, holdings, positions, available/used margin, exposure, portfolio P&L.

**Module 26: Performance Analytics** — Daily/weekly/monthly performance, strategy-wise and instrument-wise returns, risk reports.

**Module 27: Trading Journal** — Strategy version, entry/exit reason, market conditions, P&L, risk, AI review, user notes.

**Module 28: Multi-Market Manager** — Exchange adapters for NSE, BSE, MCX and global markets, each with trading calendar, timezone, session rules, currency, instrument master, tick size, lot size, contract specifications.

**Module 29: Independent Data Infrastructure** — Later phase. Planned technologies: PostgreSQL, TimescaleDB, Apache Parquet, MinIO, Redis, Polars, PyArrow, DuckDB. Independent storage for historical, tick, OHLCV, options, futures, index data, market metadata. Preserve immutable raw archives, data versions, checksums, import manifests.

**Module 30: Monitoring, Security and Administration** — Authentication, RBAC, encrypted secrets, API logs, audit logs, system health, error monitoring, database backups, disaster recovery, provider monitoring.

### 5. TECHNICAL STACK

**Frontend:** Next.js 15+, React 19+, TypeScript, Tailwind CSS, Shadcn UI, Lucide Icons, TradingView Lightweight Charts, Framer Motion.

**Backend:** Python, FastAPI, Pydantic, WebSockets, Async Processing.

**Database:** PostgreSQL, TimescaleDB, Redis, Apache Parquet, DuckDB.

**AI:** OpenAI API initially, provider-independent LLM interface, Structured Outputs, Tool Calling, AI Research Orchestration.

**Infrastructure:** Docker, Linux VPS, Nginx, Git, Automated Testing, CI/CD.

Do not unnecessarily introduce microservices at the beginning. Keep clear module boundaries and extract services when justified.

### 6. PROFESSIONAL UI/UX DESIGN

Premium professional quantitative trading terminal. Dark navy background, deep black panels, neon cyan accents, purple AI highlights, green positive / red negative, subtle borders, clean typography, professional charts, compact layout. Avoid generic admin dashboard appearance. Desktop-first, responsive, consistent design system.

**Main Sidebar:** Dashboard, AI Trading Hub, Strategy Center, Market Data, Market Scanner, Trading, Backtesting, Paper Trading, Live Trading, Portfolio & Analytics, AI Learning, Multi-Market, Reports, Tools, Settings.

**Main Dashboard:** NIFTY, BANKNIFTY, SENSEX, market selector, current session, AI market insights, market chart, active strategies, running trades, daily P&L, win rate, portfolio overview, data provider status, multi-market status, AI research activity, strategy approval queue, AI learning insights. Dashboard numbers must come from actual services. Never display fabricated live market prices as real data. When data is unavailable, display explicit disconnected, loading, or demo status.

**Strategy Center UI:** NL builder, AI research workspace, visual builder, Python editor, library, comparison, version history, backtest results, approval workflow.

**Backtesting UI:** strategy/instrument selection, date range, timeframe, capital, brokerage and slippage, run, equity curve, drawdown chart, trade history, metrics.

**Paper Trading UI:** virtual capital, balance, open positions, orders, realized/unrealized P&L, order history, strategy-wise performance.

**AI Learning UI:** completed trade reviews, winning/losing analysis, regime insights, improvement suggestions, candidate versions, approval status.

**Provider Management UI:** Upstox, Dhan, future providers, active provider, comparison mode, connection health, feed latency, historical coverage.

### 7. NATURAL LANGUAGE STRATEGY BUILDER – IMPLEMENTATION DETAILS

Dedicated backend service. Example API: `POST /api/v1/strategies/generate`.

Input:

```json
{
  "language": "mr",
  "market": "NSE",
  "instrument": "NIFTY",
  "timeframe": "5m",
  "description": "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा."
}
```

Output (structured JSON):

```json
{
  "strategy_name": "NIFTY EMA Momentum",
  "market": "NSE",
  "instrument": "NIFTY",
  "timeframe": "5m",
  "entry_conditions": [
    { "indicator": "EMA", "period": 9, "condition": "crosses_above", "target": { "indicator": "EMA", "period": 21 } },
    { "indicator": "RSI", "condition": "greater_than", "value": 55 }
  ],
  "exit_conditions": [],
  "risk_management": { "stop_loss": null, "target": null },
  "missing_information": ["Exit condition", "Position sizing"],
  "status": "draft"
}
```

Validate all AI output using Pydantic and JSON Schema. Ask clarification questions when necessary. Never invent missing user requirements. Allow editing before saving. Use deterministic strategy execution rules rather than allowing the LLM to directly execute trades.

### 8. AI LEARNING WORKFLOW

After each completed trade: save the complete trade record, capture market conditions, analyze entry and exit, evaluate risk and execution, compare expected and actual results, generate improvement hypotheses, create a new candidate strategy version, backtest the candidate, perform out-of-sample validation, paper trade the candidate, request user approval. Do not allow uncontrolled self-modification. AI recommendations must be evidence-based and traceable.

### 9. DATABASE DESIGN

Properly normalized schemas. Important entities: users, brokers, data_providers, exchanges, markets, instruments, instrument_mappings, instrument_history, contracts, historical_candles, tick_events, market_quotes, strategies, strategy_versions, strategy_conditions, backtest_jobs, backtest_results, paper_accounts, paper_orders, live_orders, positions, trades, trade_reviews, ai_research_jobs, ai_recommendations, portfolio_snapshots, data_import_jobs, data_quality_checks, audit_logs. Use proper indexes, constraints, timestamps, migrations and retention policies. Keep raw market data separate from derived data. Preserve provider source information and data provenance.

### 10. SECURITY AND TRADING SAFETY

Never expose broker API secrets in frontend code. Store credentials securely. Authentication and authorization. Complete audit trails. Validate all order requests. Risk checks before execution. Idempotency against duplicate orders. Reconcile broker orders and positions. Emergency Kill Switch. Explicit user approval for live strategy activation. Never execute arbitrary LLM-generated code. Never claim an order was executed without broker confirmation. Paper Trading must be isolated from Live Trading.

### 11. DEVELOPMENT ROADMAP

1. **Foundation** — project setup, design system, database, authentication, API architecture, provider adapter interface.
2. **Upstox Integration** — OAuth, instrument master, live WebSocket, historical data, options data, normalization.
3. **Trading Foundation** — trading engine, OMS, risk management, paper trading.
4. **Backtesting** — historical data adapter, engine, metrics, replay, optimization.
5. **Strategy Intelligence** — NL builder, visual builder, AI generation, library, versioning.
6. **AI Learning** — trade reviews, AI research, improvement suggestions, candidate validation.
7. **Second Provider** — Dhan, comparison, data quality, switching.
8. **Independent Data Infrastructure** — own historical engine, tick archive, Parquet, TimescaleDB, backup.
9. **Multi-Market** — BSE, MCX, global adapters.
10. **Production** — security audit, load testing, recovery testing, monitoring, live trading validation.

### 12. DEVELOPMENT RULES FOR CLAUDE CODE

1. First inspect the existing repository before making changes.
2. Do not overwrite existing working code without inspection.
3. Prepare a complete project architecture.
4. Create a clear folder structure.
5. Maintain a development roadmap.
6. Use reusable components.
7. Keep business logic separate from UI.
8. Keep provider-specific code inside adapters.
9. Use typed API contracts.
10. Write unit tests.
11. Write integration tests.
12. Document environment variables.
13. Never hardcode API credentials.
14. Maintain database migrations.
15. Use proper error handling.
16. Log important system events.
17. Maintain API documentation.
18. Do not implement fake live data.
19. Clearly distinguish mock/demo functionality from production functionality.
20. Do not claim features are complete until they are implemented and tested.

For every module: define requirements, design architecture, implement backend, implement frontend, connect database, write tests, verify functionality, document completion. Do not generate the entire application as one unstructured code dump. Build incrementally and preserve a working application after every phase.

### 13. FIRST TASK – START THE PROJECT

Before writing major code: analyze the repository, understand the existing UI reference, prepare the complete system architecture, folder structure, database ER diagram, API specifications, UI page map, implementation roadmap, dependencies and technical risks. Present the plan for review. Then start Phase 1. Do not skip architecture and move directly into random coding.

The ultimate objective is to create a professional, modular, secure, extensible AI-powered Algorithmic Trading Platform that can evolve from Upstox-based development to Dhan integration and eventually operate with its own independent market data infrastructure. Build this as a serious long-term software product, not a disposable prototype.
