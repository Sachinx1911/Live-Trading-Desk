# Panels (Mark 1 Stage 4.4)

Every important screen of the web app is also available as a standalone **panel**: a
chrome-less window (no sidebar, no top bar) with a stable URL. jarvis and its macOS wrapper
open a panel by URL with parameters on whichever monitor they choose (`docs/mark-1-plan.md`
§4, `docs/mark-1-build-plan.md` §4.4). The screen manager itself (which monitor, resizing,
dissolving windows) lives on the jarvis side and is not part of this repository.

## Rules

- **Panels are read-only views.** No panel places, modifies or cancels an order, changes a
  rule or risk limit, runs, confirms or cancels a protocol, acknowledges an alert or touches
  the kill switch. Owner actions that the full pages offer (recompute, rebuild, regenerate,
  acknowledge, confirm) are deliberately absent. Panels only read the same API the app uses.
- **Every panel header shows its data state** (CLAUDE.md rule 5): `Live`, `Delayed`, `Stale`,
  `Disconnected`, `Demo` or `Historical`, plus the source where there is one. Stored or
  end-of-day data is `Historical`, with its as-of date or generation time; paper P&L is
  `Demo · paper`; a missing feed is `Disconnected`, never shown as live.
- **Invalid or missing parameters** produce an error panel that names each parameter and the
  reason (`symbol required …`, `expiry: no snapshot stored for 2026-11-26`, `account: paper
  account #9 not found`). A panel never invents data for a parameter it could not resolve.
- **Auth:** panels use the app's own session (browser storage, same origin). A window without
  a session uses the development auto-login when the API allows it, otherwise the app's login
  page, which returns to the exact panel URL (path and query) afterwards.
- The header's window icon opens the corresponding full page in a window named `tp-main`
  (the main app window), never inside the panel.

## Discovery

`GET /panel/registry.json` (static, no auth, no data) returns every panel: `id`, `title`,
`description`, `path`, `template`, `example`, `params` (`name`, `type`, `required`,
`description`, `example`, `default`, `values`), `full_page`, `size` and `data_state`. Paths are
relative to the web app origin (default `http://localhost:3000`). The source of truth is
`apps/web/lib/panels.ts`, which also exports `panelUrl(id, params)` for building URLs.

Parameter types: `symbol` (NSE symbol from the instrument master, upper-cased), `symbols`
(comma-separated, at most 12), `timeframe`, `date` (`YYYY-MM-DD`, IST day), `time` (`HH:MM`,
24 h IST), `boolean` (`1`/`0`, also `true`/`false`), `integer` (id). Unknown parameters are
ignored.

## Panel list

| Panel | URL example | Params (required in bold) | Full page |
|---|---|---|---|
| Chart | `/panel/chart?symbol=NIFTY&tf=5m` | **symbol**, tf (`1m 5m 15m 30m 1h 1d`, default `5m`) | `/market` |
| Option chain | `/panel/option-chain?symbol=NIFTY&expiry=2026-11-25&greeks=1` | **symbol** (`NIFTY`, `BANKNIFTY`), expiry (default nearest stored), greeks (default `0`) | `/market/option-chain` |
| OI change | `/panel/oi-change?symbol=NIFTY&date=2026-11-20&from=09:15&to=15:30` | **symbol**, date (default today IST), from (`09:15`), to (`15:30`, after from), expiry (default nearest stored that day), range (strikes each side, default 10, 0 = all) | `/market/oi-change` |
| Quotes | `/panel/quotes?symbols=NIFTY,BANKNIFTY,INDIAVIX` | **symbols** | `/market` |
| Positions | `/panel/positions?account=1` | **account** (paper account id), closed (default `0`) | `/paper/positions` |
| Alerts | `/panel/alerts` | unread (default `0`), limit (1-300, default 100) | `/alerts` |
| Market breadth | `/panel/breadth` | — | `/dashboard` |
| Regime | `/panel/regime?symbol=NIFTY` | symbol (default all tracked indices), days (5-120, default 30) | `/dashboard` |
| Scanner | `/panel/scanner?preset=1` | **preset** (preset or saved scan id) | `/scanner?scan=<id>` |
| Backtest result | `/panel/backtest?job=42` | **job** | `/backtesting/<job>` |
| Evening brief | `/panel/brief?date=2026-11-20` | date (default latest stored) | `/reports` |
| News | `/panel/news?symbol=RELIANCE` | symbol (default all), limit (1-200, default 50) | `/news` |
| Protocol run | `/panel/protocol-run?id=7` | **id** | `/protocols` |

What each panel shows:

- **Chart**: candles from storage with the forming bar from live ticks; fills the window.
  Historical when the feed is down.
- **Option chain**: latest stored snapshot for the expiry, ATM row scrolled into view; Greeks
  columns with `greeks=1`. State is the snapshot's freshness from the API.
- **OI change**: call/put OI change, PCR and spot hero numbers, per-strike bars spread across
  the window width; the snapshot times actually used are in the header source.
- **Quotes**: one tile per symbol (big last price, change, its own freshness badge); unknown
  symbols get a tile saying so. Header state is the market feed.
- **Positions**: equity, unrealized, realized, cash and the account's open positions (paper
  only; the live account is not exposed as a panel).
- **Alerts**: stored alerts, newest first, without the acknowledge buttons.
- **Breadth**: latest NIFTY 50 breadth and the stored history chart (end of day).
- **Regime**: one index's 30-day strip and today's labels, or every tracked index.
- **Scanner**: the preset's result over the EOD snapshot (first 200 rows; sorting is local).
- **Backtest**: full-width status banner (`BACKTEST #42 · SUCCEEDED` / `FAILED` in red), key
  metrics, equity and drawdown filling the rest.
- **Brief**: the stored evening brief sections.
- **News**: stored headlines (publisher links open outside), optionally for one symbol.
- **Protocol run**: one run with each step's stored result; refreshes every 1.5 s while the
  run is open. Confirm and cancel stay on `/protocols`.

## Sizing

Panels are built for separate windows from about **480×320** up to a full 4K screen. The
header is 32 px; the body fills the rest and scrolls only when the content cannot fit (long
tables, long lists). Charts follow the window size (chart, backtest curves, OI-change bars).
Narrow headers drop the source text and the read-only marker first; the title, the data-state
badge and the full-page link stay. `size.preferred` in the registry is a hint for the window
manager, not a requirement.

## Opening panels today

Each corresponding full page has a small "Open as panel" icon (picture-in-picture) next to its
title actions: market chart and watchlist, option chain (keeps the Greeks toggle), OI change
(keeps symbol, day, window, expiry, range), alerts, paper positions, dashboard regime and
breadth tiles, scanner (when an unmodified preset or saved scan is active), backtest detail,
evening brief, news and every protocol run. It opens a browser pop-up window at the panel's
preferred size; middle-click opens it in a tab.
