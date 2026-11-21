# Mark 1 plan: JARVIS

Planning record of the discussion with the product owner on 2026-11-21. Nothing in this
document is built unless `docs/progress.md` says so. It extends, and does not replace,
`docs/MASTER_PROMPT.md`, the ADRs and `CLAUDE.md`; the safety rules there stay in force.

## 1. Where the product is going

The platform does not stay a click-through trading terminal. Its final form is one AI
assistant, **JARVIS**, that the owner commands in Marathi, Hindi or English and that does
the work: shows data, runs scans and backtests, drafts rules, manages paper strategies,
watches the market and reports back.

Versions are named like Iron Man suits.

| Version | Scope |
|---|---|
| **Mark 1** | The whole first complete product described here, ending at **paper trading** with a **chat** interface |
| **Mark 2** | **Live trading** with real money, and **voice** |

"Mark 1" is not the build that exists today; today's build is the foundation of Mark 1.

## 2. JARVIS

### 2.1 Structure

- JARVIS is the **single main agent** and the only one that talks and reports to the owner.
- There is **no fixed roster of specialist agents**. When a task needs help, JARVIS creates
  helper agents for that task underneath itself and they end when the task ends.
- Helpers never talk to the owner, never get more authority than JARVIS, and never touch
  money-related actions.
- What we build is therefore a **catalogue of tools**, not a set of agents: every action of
  the platform (show a chart, run a scan, run a backtest, draft a rule, start or stop a
  paper strategy) exposed as one typed, named tool with a risk level. The existing typed
  API is the base for this; the intended standard for exposing tools is MCP, so the model
  behind JARVIS stays replaceable (OpenAI first, as already decided).

### 2.2 One name, four internal modes

The owner addresses only "JARVIS". Internally it works in four styles.

| Mode | When | Behaviour |
|---|---|---|
| JARVIS | Market closed | Detailed analysis, planning, backtest results, advice |
| FRIDAY | Market open | Short and fast: status, pattern call-outs, urgent notices |
| EDITH | Always, in the background | Watches everything (instruments, OI, feed, positions, risk, rules) and raises alerts. It only watches and warns; it never acts on its own |
| KAREN | When asked | Teacher and coach: explains concepts, reviews trades, shows how a rule performed |

Speaking up unprompted (EDITH) is a core trait of the product, not a side feature.

### 2.3 Risk levels for every tool

| Level | Kind of action | What JARVIS does |
|---|---|---|
| Green | Read only: charts, scans, reports, status | Does it immediately |
| Yellow | Changes: new draft, backtest, start or stop a paper strategy, import | Paper-trading changes: does it and reports (standing permission, see below). Other changes: states what it will do and asks once |
| Red | Money or safety: live orders, risk limits, live approval, turning the kill switch off, applying a new hard rule | Risk engine check, explicit owner confirmation, and only through the deterministic gateway |

Turning the kill switch **on** is always immediate.

**Standing permission for paper trading** (owner decision, 2026-11-21). JARVIS does not ask
before these; it acts and reports: start, stop or pause a paper strategy; run a backtest or
a replay; create a strategy draft or a new version; close paper positions. It still asks
for everything red: adding, changing or removing a hard trading rule, changing risk
limits, turning the kill switch off, approving a strategy for live, and anything with real
money. With the permission in place, every paper order still passes the risk engine and
the owner rules, every change is logged and reported at once, and "stop" or "undo that"
from the owner takes effect immediately.

Rules that hold for JARVIS and every helper:

- No agent touches the database or a broker directly; only catalogue tools.
- The owner's hard trading rules (`docs/trading-rules.md`) cannot be bypassed by any agent.
- Every number comes from a tool. If data is missing JARVIS says so; it never invents one.
- Every action is logged with what was done, why, and on which data. AI spend has a daily cap.
- `CLAUDE.md` rule 1 stands: no LLM places, modifies or cancels an order. A spoken order in
  Mark 2 still goes through the execution gateway, the risk engine and owner confirmation.

### 2.4 Protocols

A protocol is a named, fixed bundle of actions run by one command. Initial set:

| Protocol | Does |
|---|---|
| Market Open | Checks broker session, feed, collector; reports yesterday's regime, PCR, today's events |
| Market Close | Position status, day report, data completeness, preparation for tomorrow |
| Shutdown | Stops all paper strategies and closes positions (asks first) |
| Clean Slate | Kill switch on, all new entries blocked (immediate) |
| Health Check | State of every process in one answer |
| Review | KAREN's review of the day's or week's trades |

The owner can define more. A protocol can also carry a screen layout (section 4).

### 2.5 How it gets built

Lessons taken from how this is done elsewhere: keep execution and risk deterministic, let
the model choose tools rather than compute, widen authority in steps, and test the agent
like software.

1. Tools first, JARVIS second. Tools are built and tested without any AI.
2. Read-only tools first; then paper-trading changes; rules and approvals last.
3. A fixed test list of real owner commands (Marathi, Hindi, English) with the expected
   tool calls, re-run whenever the prompt or model changes.
4. Helpers only where a single agent proves insufficient.

## 3. Features in Mark 1

### 3.1 Already built (to be exposed as tools)

Market data and charts, market regime, scanner (14 presets), backtest, replay, paper
trading, strategy approval workflow, risk engine and kill switch, data import, visual
strategy builder, owner-rule registry with rule 1 `pcr_guard`.

### 3.2 To build

| Feature | What | Level |
|---|---|---|
| Intraday OI history | Store per-strike OI through the day for tracked underlyings | Background |
| Old OI data | Back-fill expired option contracts (October 2026 first) from Upstox Plus | Yellow |
| OI Change chart | Like Sensibull's "OI change vs strike": pick a day and a time window, per-strike put/call OI change bars, total call and put OI change, PCR, spot at start and end | Green |
| Greeks view | Option chain with delta, theta, gamma, vega, IV per strike | Green |
| OI and Greeks in the engine | PCR, OI change and delta usable in the strategy DSL, backtest and replay | Yellow |
| Owner trading rules | More rules in the registry as the owner gives them | Red to apply |
| Protocols | Section 2.4 | Mixed |
| Proactive alerts | Rule about to trigger, feed down, signal fired; in-app and Telegram | Green |
| Reports | End-of-day report and trade review | Green |
| Dhan | Second broker and backup data source (Access Token mode) | Background |
| JARVIS core | Tool catalogue, chat surface, confirmation flow, helper agents, memory, audit log, spend cap | Section 2 |
| Workspace manager | Section 4 | Section 4 |

### 3.3 Build stages inside Mark 1

| Stage | Content | Needs AI |
|---|---|---|
| 1 | OI history, old data from Upstox Plus, OI Change chart, Greeks view | No |
| 2 | OI, PCR and Greeks in backtest and replay; the owner's next trading rules | No |
| 3 | Protocols, proactive alerts, reports, Dhan | No |
| 4 | Every action exposed as a tool; read-only JARVIS with chat; desktop shell and workspace manager | Yes |
| 5 | JARVIS that makes changes (backtests, paper trading, rule drafts), helpers, KAREN mode | Yes |

Stages 1 to 3 need no LLM, which keeps the owner's earlier decision that the OpenAI key is
used last.

## 4. Screens, windows and motion

Target: working with the product should feel like Tony Stark working with JARVIS, as far
as real monitors allow. The owner does not arrange windows; JARVIS does.

Requirements from the owner:

1. JARVIS knows how many monitors are connected (1, 2 or 3).
2. Requested content ("show the option data") opens on the main screen.
3. If the owner is already working on the main screen, it opens on another screen instead.
4. While a task runs, windows resize and re-arrange themselves to make room.
5. When the task is done, its windows go away.

Decided (owner, 2026-11-21): a **desktop app** (a shell around the existing web app),
because a browser tab cannot fully control windows across monitors. Platform is **macOS
only**. The owner trades with **2 screens**.

| Situation (2 screens) | JARVIS does |
|---|---|
| Content requested, main screen idle | Opens it on the main screen |
| Owner is working on the main screen | Opens it on the second screen |
| Second screen already has panels | They shrink to make room |
| Task finished | Its panels dissolve |
| Only one screen connected | Panels open in a side split |

What stays permanently on the second screen (for example chart, positions, alerts) is
still to be chosen.

- Everything is a **panel** (option chain, OI chart, backtest result, positions). JARVIS
  opens, moves, resizes and closes panels; new screens are built as standalone panels from
  now on so they can be placed anywhere later.
- The "busy" screen is the one with current mouse and keyboard activity.
- 3 screens: main for the owner's work, second for JARVIS panels, third for always-on views.
  2 screens: main for the owner, second for JARVIS. 1 screen: panels open in a side split
  and the owner's window shrinks to fit.
- Panels are temporary unless the owner says keep. Task panels show progress and leave
  when the task ends.
- One focused panel large and central, the rest small at the edges; a single command can
  change the whole layout; protocols can carry a layout.
- Motion: panels unfold from a point, slide between screens, dissolve on close. Fast and
  short while the market is open (under about half a second), more expressive when closed,
  with a calm option that minimises motion.

Not achievable and their substitutes: floating holograms (large screens and frameless
windows), mid-air hand gestures (mouse or trackpad flicks and commands now; voice in
Mark 2).

## 5. Look

The owner wants the dashboard to look like the JARVIS interface from the films (dark
field, cyan line work, rings and gauges, glass panels, a central core). A first mock-up
was shown in the planning session, and the owner then supplied a reference image (below).
**The visual design discussion is postponed by the owner** and resumes when they raise it. Open when it does: whether the HUD look is an
additional theme next to the existing TradingView-based dark and light themes, or replaces
them; and what sits at the centre of the dashboard.

### Design reference: the workshop monitors

On 2026-11-21 the owner supplied a film still of the Iron Man workshop desk and decided
that our desktop design is to be built after the monitors in it. This reference takes
priority over the HUD mock-up drawn in the planning session. The image itself is not in
the repository (the repository is public and the still is copyrighted); the owner has it,
and this is what it shows:

- Thin, nearly frameless glass monitors on arms, angled around the desk, plus a larger
  screen behind. The interface looks as if it floats on dark glass.
- Near-black, blue-tinted background. One cyan / ice-blue for all line work and text.
  Small orange accents only for highlighted or warning items.
- A dense mosaic of many small panels in a tight grid, with thin outlines and almost no
  filled blocks.
- Circular elements everywhere: ring gauges, radial dials, rows and columns of round icons.
- One large hero graphic per screen (a wireframe schematic on one, a big circular readout
  on another), surrounded by small data panels, thin bar charts, small tables and text
  columns.
- The rear screen is a feed wall: a grid of thumbnails with a video tile.
- Very small technical type, a soft glow on lines, slight transparency.

How it maps to the owner's two screens:

| In the reference | In the product |
|---|---|
| Screen with the hero graphic | Main screen: the chart or the requested content in the centre, small panels around it |
| Screen of ring gauges | Second screen: PCR, VIX, risk and OI-change gauges, and JARVIS's panels |
| Feed wall | Grid of alerts, signals and positions |
| Orange highlights | Warnings and rules close to triggering |

One constraint the reference does not have: prices and key numbers must be readable at a
glance, so the style is kept but important figures are set larger than in the film.

## 6. Data sources

- The exchange refreshes open interest about every 3 minutes (as stated on Sensibull's OI
  page; to be measured with `python -m collector.oi_cadence` in a live session). OI-based
  rules are therefore evaluated on 3 to 5 minute windows, not on 1-minute bars.
- Direct exchange feeds are for licensed vendors and institutions; brokers are the route
  for this product, and for OI nothing would be gained from a direct feed.
- The owner has accounts with **Upstox** and **Dhan**.
  - Upstox: main data source and broker (in use).
  - **Upstox Plus**: recommended for old option data. It opens the expired-instruments
    endpoints; expired contracts have 1-minute candles that include open interest, per
    individual strike. No monthly fee was found; brokerage is higher (about ₹30 per order),
    which matters only once live trading starts. How far back the data goes is not
    documented and must be checked on the first day.
  - Dhan: second broker and backup. Its expired-options data is addressed by distance from
    ATM (about ATM ±10 strikes for index options) and includes historical IV, behind a paid
    data subscription (about ₹499 a month when last published). Taken only if historical IV
    or a second source is needed.
- NSE F&O bhavcopy gives free end-of-day OI per strike and can back-fill day-level history.
- SEBI's retail algo rules (static IP, registration above an order-rate threshold) must be
  checked for the chosen broker before live trading in Mark 2.

### Candidate model: Jev (TypeSafe AI)

Looked at on 2026-11-21 (https://typesafe.ai/). A decision model rather than a chat model:
it returns typed decisions with a confidence value, and the vendor claims it is far faster
and cheaper than an LLM. It is in early access and the claims are unverified. **Deferred by
the owner**: it is not part of the plan now and will be considered only where a real need
appears. Candidate places then: recognising the intent of a command, classifying its risk
level, filtering alerts, tagging trades, sorting backtest results. Never inside the
backtest or execution engine (results must be reproducible, free of look-ahead, and no
model decides orders), and not for conversation, which it does not do.

## 7. What the owner supplies

| When | What |
|---|---|
| Before stage 1 | Switch the Upstox account to the Plus plan |
| Stage 2 | The next trading rules |
| Stage 3 | Dhan access token (entered on `/settings/brokers`, never in chat or git); Telegram bot token |
| Before stage 4 | OpenAI key in the server `.env` |

## 8. Open decisions

1. Design questions in section 5, when the owner reopens them.
2. Keep or revert the collector change made during planning (option chain every 3 minutes,
   commit `06bd9ed`).
3. What stays permanently on the second screen.
4. The owner's next trading rules.

Closed on 2026-11-21: paper trading gets standing permission (section 2.3); desktop app on
macOS with 2 screens (section 4); Jev deferred (section 6).

## 9. Working agreement

While the owner is planning, nothing in the repository is changed. Items raised in a
planning discussion are recorded here; building starts only on an explicit go-ahead.
