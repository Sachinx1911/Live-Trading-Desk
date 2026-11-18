# 09 · Design reference: TradingView (reverse-engineered)

Evidence captured 2026-11-18 from `tradingview.com/chart`, `/screener`, `/heatmap/stock` in the
built-in browser: CSS custom properties read from the loaded stylesheets, computed styles of
live elements in the dark theme (toggled in the TradingView menu) and the light theme, canvas
pixel sampling for chart surfaces. No TradingView code, icons, fonts or images are copied;
this document records *measurements* we use as design inspiration for our own tokens.

Tooling note: `morluto/rea` (REA) was reviewed; its website tools need Chrome's debugging port
and an MCP registration. The same evidence (stylesheet variables, computed styles, DOM
metrics) was captured directly here, so REA is not required for this task.

## 1. Palette (named scales from `:root`)

TradingView's global palette is a set of 50–900 scales. Values below are the ones we adopt.

| Scale | 50 | 100/150 | 200/250 | 300/350 | 400/450 | 500/550 | 600/650 | 700/750 | 800/850 | 900 |
|---|---|---|---|---|---|---|---|---|---|---|
| cold-gray | #f9f9f9 | #f2f2f2 / #ebebeb | #dbdbdb / #c9c9c9 | #b8b8b8 / #a8a8a8 | #9c9c9c / #8c8c8c | #808080 / #707070 | #636363 / #555555 | #464646 / #303030 | #222222 / #131313 | #000000 |
| tv-blue | #e3effd | #bbd9fb | #90bff9 | #5b9cf6 | #3179f5 | **#2962ff** | #1e53e5 | #1848cc | #143eb2 | #0c3299 |
| minty-green (up) | #daf2ee | #ace5dc | #70ccbd | #42bda8 | #22ab94 | **#089981** | #06806b | #056656 | #004d40 | #00332a |
| ripe-red (down) | #ffebec | #fccbcd | #faa1a4 | #f77c80 | #f7525f | **#f23645** | #cc2f3c | #b22833 | #991f29 | #801922 |
| tan-orange | #fff3e0 | #ffe0b2 | #ffcc80 | #ffb74d | #ffa726 | #ff9800 | #fb8c00 | #f57c00 | #ef6c00 | #e65100 |
| banana-yellow | #fffde7 | #fff9c4 | #fff59d | #fff176 | #ffee58 | #ffeb3b | #fdd835 | #fbc02d | #f9a825 | #f57f17 |
| grapes-purple | #f3e5f5 | #e1bee7 | #ce93d8 | #ba68c8 | #ab47bc | #9c27b0 | #8e24aa | #7b1fa2 | #6a1b9a | #4a148c |
| deep-blue | #ede7f6 | #d1c4e9 | #b39ddb | #9575cd | #7e57c2 | #673ab7 | #5e35b1 | #512da8 | #4527a0 | #311b92 |
| iguana-green | #e8f5e9 | #c8e6c9 | #a5d6a7 | #81c784 | #66bb6a | #4caf50 | #43a047 | #388e3c | #2e7d32 | #1b5e20 |

Dark-mode "a" variants exist for the semantic colours (e.g. minty-green a600 #24b29b, a700
#1b7667, a800 #10443b, a900 #082621; ripe-red a600 #cc2929, a700 #802028, a800 #4d191d,
a900 #331f20; tv-blue a700 #143a87, a800 #142e61, a900 #132042) — used for tinted
backgrounds behind coloured text on dark surfaces.

## 2. Dark theme, as rendered (computed)

| Role | Value | Where measured |
|---|---|---|
| Page / chrome background | `#222222` (cold-gray-800) | `body`, bottom tab bar |
| Chart pane, left tool rail, right widget bar, top bar | `#000000` | layout areas |
| Raised control (toolbar button, symbol pill) | `#303030` (cold-gray-750) | top toolbar button |
| Primary text | `#dbdbdb` (cold-gray-200) | symbol title |
| Secondary text | `#b8b8b8` (cold-gray-300) | body text, toolbar labels |
| Muted / disabled text | `#8c8c8c` (450), `#555555` (650) | icon buttons, "Upgrade" |
| Dividers | `#303030`, `#222222` | separators between panels |
| Positive change text | `#22ab94` (minty-green-400) | watchlist change |
| Negative change text | `#f23645` (ripe-red-500), highlight `#f7525f` | watchlist change, last price flash |
| Accent | `#2962ff` (tv-blue-500) | links, selected state, "Save" |

Observation: in dark mode TradingView uses **two surfaces only** (black panes, #222 chrome)
and separates regions with 1px `#303030` lines or tone changes, never with borders around
cards. Hover/selected states are tone shifts (#303030 → lighter), not outlines.

## 3. Light theme, as rendered

| Role | Value |
|---|---|
| Page background (chart page) | `#ebebeb` (cold-gray-150) |
| Page background (screener/heatmap) | `#ffffff` |
| Panels / table | `#ffffff` |
| Raised control | `#f2f2f2` (cold-gray-100) |
| Primary text | `#000000`; secondary `#464646`; muted `#707070` |
| Dividers / table row lines | `#f2f2f2` and `#ebebeb` |
| Selected pill | `#222222` background, white text |

## 4. Typography

- Font stack: `-apple-system, system-ui, "Trebuchet MS", Roboto, Ubuntu, sans-serif`
  (system UI font; no web font download). We keep Inter + JetBrains Mono but adopt the sizes.
- Base size **14px / 400**, used for ~80% of text (1,835 of 2,300 sampled nodes).
- Secondary sizes: 13px (dense tables), 12px (axis labels, captions), 11px and 10px (badges,
  legend details). Headings: 24px/600 (page title), 28px (big price in the symbol card).
- Section labels in panels are 11–12px, uppercase, muted (`INDICES`, `STOCKS`).
- Numbers are tabular; prices right-aligned in tables.

## 5. Controls and density

| Control | Measurement |
|---|---|
| Top toolbar | 38px tall, black; buttons 28px tall, **pill radius 14px**, no border, bg `#303030` for the active symbol/interval pill, transparent otherwise |
| Left drawing-tool rail | 52px wide, icon buttons ~34px, radius 4px on grouped buttons (4px 0 0 4px / 0 4px 4px 0) |
| Right widget bar | 346px wide; icon tab rail on the far right (28px icons), page content with 28px-tall section headers (600 weight) |
| Watchlist row | ~34px tall; symbol (600 weight) + last price + change coloured, 14px |
| Bottom tab bar | 28px, `#222` |
| Screener tabs (Overview, Performance, Technicals…) | 28px pills, selected = `#222` bg + white text, padding 0 11px |
| Screener preset chips ("All stocks", "Most capitalized"…) | 28px pills, 1px `#ebebeb` border, white bg |
| Filter chips (Index, Price, Chg %, Mkt cap, P/E…) | 34px, radius 8px, 1px `#ebebeb` border or borderless with chevron |
| Primary button ("Get started") | 36–40px, radius 36–40px (pill), dark bg |
| Icon sizes | 18×18 (toolbar), 14×14 (inline), 28×28 (rail tabs), 12×13 (chevrons) |
| Screener table | header row 50px, 700 weight; body rows **41px**, cell padding `0 12px` (first column `0 12px 0 20px`), 1px `#f2f2f2` row lines, no zebra striping, numbers right-aligned, symbol cell = logo + ticker (600) + name (muted) |

## 6. Chart surface (canvas pixel sampling)

- Candles: up `#089981`, down `#f23645` (body and wick), volume bars in the same hues at
  roughly 45–50% opacity (sampled `rgb(146,210,204)` on white, `rgb(19,83,77)` /
  `rgb(120,42,40)` on black).
- **No visible grid in the default dark theme**: four horizontal scanlines and one vertical
  scanline of the main pane contained only black plus candle colours. Light theme: white pane,
  grid effectively invisible too. Our charts currently draw a dotted grid; drop it or make it
  ≤ 6% white.
- Price axis: black background, label text `#b8b8b8` (12px), last-price chip filled with the
  candle colour (`#089981` / `#26a69a` band) with white text.
- Legend (top-left of pane): title 16px, values 13px, rendered at 50% opacity over the pane
  (`rgba(255,255,255,.5)` text on dark); OHLC values coloured up/down.
- Symbol card in the widget bar: price 28px/600, change 16px/600 in the up/down colour.

## 6a. Overlays: dialogs, menus, inputs (dark)

| Element | Measurement |
|---|---|
| Modal dialog (symbol search) | 840×680, radius **20px**, surface `rgba(19,19,19,0.85)` with backdrop blur (glass), inset 1px ring `rgba(140,140,140,0.10)`, shadow `0 0 2px #000`, `0 0 ... #000` |
| Modal backdrop | `rgba(26,26,26,0.40)` |
| Search input | 16px text, no border, inside a 40px-tall wrap (`padding 6px 0`, radius 8px); the magnifier icon leads, a clear/close icon trails |
| Category chips inside dialogs (All, Stocks, Funds, Futures, Forex, Crypto, Indices, Bonds, Economy, Options) | 28px pills, padding 0 11px: selected `#f2f2f2` bg + black text, others `#222` bg + `#b8b8b8` text |
| Small popup (Change interval) | centered 280px card, same glass surface, title 16px, a 36px input with a 1px `#2962ff` focus ring, hint text 12px muted |
| Context/main menu | 260px wide, padding 6px 0, items 14px `#b8b8b8`, toggles (switch) on the right, dividers `#303030` |
| Result rows (symbol list) | 48px: logo 18px, ticker 14px `#dbdbdb`, description 13px muted, exchange badge 12px + 18px round flag/exchange logo at the right |

## 7. Features worth borrowing (the owner asked to note these for later)

**Screener** (`/screener`)
- Preset screens as pill chips: All stocks, Most capitalized, Highest net income, Highest
  cash, Close to new high, Healthy growth technology, High capital efficiency, Strong
  performance small caps, Dividend princes/kings, Bullish and undervalued, Large efficient
  and innovative, Doubled, … ("More").
- Filter chips in a row: AI (natural-language filter), market (US…), Watchlist, Index, Price,
  Chg %, Mkt cap, P/E, EPS dil growth, Div yield %, Sector, Analyst rating, Perf %, Revenue
  growth, PEG, ROE, Beta, Recent/Upcoming earnings date, "+" more filters.
- Column sets as tabs: Overview, Performance, Technicals, Extended hours, Forecasts,
  Valuation, Dividends, Profitability, Income statement, Balance sheet, Cash flow, Per share.
- Overview columns: Symbol (logo + ticker + name), Price, Chg %, Vol, Rel vol, Mkt cap, P/E,
  EPS dil TTM, EPS dil growth TTM YoY, Div yield % TTM, Sector, Analyst rating.
- Save screen, table/heatmap view toggle, 100-row pages, column settings.

**Heatmap** (`/heatmap/stock`)
- Controls: data source (index), block size (market cap…), block colour (Change 1D %…),
  grouping (sector…), "Open in Screener"; legend −3%…+3% in five steps each side; blocks show
  ticker + change, sector headers with chevrons; dark green→red diverging scale.

**Chart page**
- Symbol search pill, interval pill, chart type, indicators, alert, replay, undo/redo,
  layout, save, quick search, settings, fullscreen, snapshot, "Trade", "Upgrade".
- Right widget rail: Watchlist, Details (big price + change + market status + key facts
  card), News, Alerts, Data window, Hotlists, Calendar, Notes, Chat, Ideas.
- Bottom: Stock screener / Pine editor / Strategy tester / Trading panel tabs; timeframe
  quick buttons 1D 5D 1M 3M 6M YTD 1Y 5Y All; "Go to" date; timezone; ADJ.
- Watchlist sections (INDICES / STOCKS) collapsible; flag/colour tagging of symbols.

## 8. What to change in our app (proposal, not yet applied)

1. Surfaces: replace navy/black-panel pairing with **black panes + `#222` chrome**, tone
   dividers (`#303030`) instead of translucent borders; keep an optional cyan accent only for
   "AI" elements, use `#2962ff` as the primary accent.
2. Controls: 28px pill buttons for toolbar/tabs, 34px/8px-radius filter chips, 41px table
   rows with `0 12px` padding, 50px bold header rows, no zebra.
3. Typography: 14px base everywhere (we currently mix 11–13px), 12px axis/captions, 600 for
   symbols, uppercase 11px muted section labels.
4. Layout: top toolbar 38px, collapsible icon rail on the left (52px) instead of the wide
   grouped sidebar, right widget bar 346px with icon tabs on the chart/market pages.
5. Chart: adopt the minty/ripe candle pair and faint grid; last-price chip.
6. Light theme: white panels on `#ebebeb` page, `#f2f2f2` row lines — only if the owner asks.

Open items still to measure (need the browser pane undisturbed): hover/active tones,
dropdown and dialog surfaces, tooltip style, input fields, transition timings, exact grid
line colour from the canvas.
