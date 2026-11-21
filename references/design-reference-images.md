# Design reference images (owner, 2026-11-21)

Eighteen images the owner chose as the **design reference for the JARVIS desktop**. They extend
`docs/mark-1-plan.md` §5 (workshop monitors). Six are film stills (Iron Man, Avengers: Age of
Ultron, Spider-Man: Brand New Day), one is a product photo of a transparent display desk, one is a
fan recreation. All are third-party material: kept locally in `references/_images/` as `NN-short-name.ext` matching the numbers below (git-ignored,
public repo) and **never used in the product**; only the design language below is ours to use.

## The images

| # | Shows | What to take |
|---|---|---|
| 1 | Workshop desk: many small monitors around the chair, each a dense blue panel; two plain monitors in the foreground | Many screens, each one job; dark room, the screens are the light source |
| 2 | Transparent glass monitors on a curved desk; a health readout with a big red timer `07:23:14`, a percentage, a ring diagram; "VIDEO CONFERENCE" panel on another screen | **One big number with a label** as the hero of a panel; red only for the critical value; glass panels you can see through |
| 3 | Curved desk wrapped with a row of glass monitors; holographic wireframes (car, bike) floating in the room | A **wrap-around row** of panels at the same height; wireframe = "object being worked on" |
| 4 | Lab with large floating holograms: a circular ring interface in front of the user, a row of vertical cards to the side | **Concentric ring** as the central control; **stack of vertical cards** to browse many results |
| 5 | Real desk (AUO transparent display): a transparent screen with a **circular clock/progress ring** "7:15 AM", next to ordinary monitors | Proof the look works on real hardware: one ring widget on the side screen, normal work on the main ones |
| 6 | Film still vs a fan-built "Inhibitor Command Center": hormone level bars HUMAN/ARACHNID, DNA helix, firmware compile window with hex dump, "LOADING" bar | **Two opposing vertical meters** (human vs arachnid ≈ calls vs puts); a **task window with progress** that pops over the dashboard; the fan build shows a web UI can match the film |
| 7 | "ULTRON PROGRAM 8.7 · SCEPTER INTEGRATION": wide blue screen, monospaced labels, data grids, a wireframe body, a big banner `TEST-77 · INTEGRATION SUCCESSFUL`; a second screen shows the same test **FAILED** in red | **Full-width status banner** for the result of a run (backtest passed / failed); orange for headers, white for the hero, red for failure; numbers in tidy grids |
| 8 | JARVIS UI: a glowing core inside a curved arc, scales of small red/white values on both sides, a "JARVIS · ESTABLISHING COMMUNICATION" dialog, a table of connections with TRUE/FALSE values, numbered tiles `01…06` | **The assistant as a core with status line**, a modal for "what JARVIS is doing now", **tables with state columns**, **numbered tiles** (screens, slots or protocols) |
| 9 | Penthouse room (The Avengers): a ring of free-floating glass panels around the room, each a **dossier card** for one person or object (photo, name, ID number, a few stats, a small icon or emblem), plus video, a map and a schematic; two people stand in the middle and look at them | **Entity cards**: one card per thing with photo/icon, name, id and 3–4 key figures, arranged around a centre. For us: one card per instrument, strategy or open position (symbol, LTP, change, regime, P&L), JARVIS lays out the ones relevant to the question; video tile = live chart |
| 10 | Workshop: suit model on a large screen with build status, small terminal panels, a dark log window with an "ACCESS GRANTED" badge | **Access/PIN screen** as a small badge over a log; a slowly rotating hero model while idle |
| 11 | "Periodic" screen: a big grid of element tiles, a few flagged red, around it ring scanners, molecular recognition list, `HEALTH STABILITY 67%` and a red countdown | **Tile grid as a heatmap**: NIFTY 50 / sector tiles coloured by change, red tiles = flagged (rule hit, gap, alert); the grid is the hero, small analytic panels around it |
| 12 | Connection console: left icon rail, globe with satellites, "WAN ACCESS MANAGER · Establishing link protocols" progress, "VERIFYING USER", technical database schematic, right-side tree of data inputs | **Start-up / connect sequence**: broker session, feed, collector shown as "establishing link" steps with progress; left icon rail like ours; right-hand tree for health details |
| 13 | A real Windows desktop skin (Rainmeter style): radial launcher ring in the centre, big clock and date block, CPU/network meters, calendar | Proof it can be a real daily desktop. **Radial command ring** for protocols; a big clock/date + market session block |
| 14 | IP address screens: very large monospaced numbers, a list with one row highlighted amber, a DHCP table, map, `65%` dial, small round menu icons | **Huge monospaced values** for the key figure, **selected row in amber**, compact tables with status text; round icon menu |
| 15 | Navigation console: map as the hero with a plane marker and callout card, telemetry list on the left (altitude, speed, times), command queue table on the right, mode tabs on top | Main-screen layout: **hero visual in the centre, telemetry column left, queue/status table right, mode tabs top**. For us: chart centre, quote/greeks column left, orders/alerts right |
| 16 | Same console with a 3D globe and time-zone bands (`-5HRS ZULU`…) | **Market sessions on a globe / time band**: which exchanges are open now (multi-market, Phase 9); time bands for IST session windows |
| 17 | Component locator: modal "LOCATING MISSING COMPONENT" with progress, red "CRITICAL COMPONENT MISSING", right-side diagnostic tree with red missing items, dial row at the bottom | **Search/diagnose task modal** with progress; **missing items in red in a tree** = data-gap report, missing chain snapshots, failed jobs |
| 18 | Modern energy dashboard (not film): isometric 3D blocks connected by glowing teal lines, KPI row on top, line charts below, calm dark grey | Clean, highly readable alternative to the film look. **System map**: broker → collector → database → trader → paper account as isometric blocks with live status on the links; KPI row on top |

## Design language extracted

| Token | Value / rule |
|---|---|
| Background | Near-black navy `#05080f`–`#0a1220`; panels slightly lighter `#0c1a2b` at 70–85 % opacity |
| Primary line and text | One cyan / ice-blue `#5fd4ff` (lines), `#bfefff` (text); thin 1 px outlines, soft glow (blur 4–8 px, low alpha) |
| Secondary accent | Amber/orange `#ffb347` for headers, highlights and "close to a rule" warnings |
| Critical | Red `#ff4d4d` only for failure, loss limit, kill switch, PCR rule triggered |
| Success | White hero text on cyan, or the existing positive green for P&L only |
| Type | Monospaced, uppercase labels, wide letter spacing (0.08–0.15 em), 10–11 px for labels; **hero numbers 28–48 px**, tabular figures |
| Shapes | Rings and arcs (gauges, core, clock), thin rectangles with cut or bracketed corners, tick-mark scales, dotted leaders |
| Layout | Dense mosaic of small panels around **one hero element** per screen; status banner across the full width for results; vertical card stacks for lists of results |
| Motion | Panels unfold from a point, scan-line sweep on load, numbers count up, rings rotate slowly; all under ~0.5 s while the market is open (plan §4) |

## How it maps to our screens

| Reference element | In the product |
|---|---|
| Core in an arc (8), ring (4, 5) | Screen 2 centre: JARVIS core showing state (listening, working, alert) and the current mode |
| Big number with label (2) | Index price, day P&L, PCR, VIX: one large figure per panel |
| Opposing meters (6) | Call vs put OI change; long vs short exposure |
| Status banner (7) | Backtest / replay / protocol result: `BACKTEST #42 · PASSED` or `FAILED` in red |
| Task window with progress (6) | A running JARVIS task (backtest, import, scan) pops up with live steps and narration, then dissolves |
| Vertical card stack (4) | Top backtest variants, scanner hits, alerts feed |
| Numbered tiles (8) | Protocol buttons or saved layouts |
| Dossier cards around a centre (9) | "Show me my positions / the strategies running": one card each, grouped around the JARVIS core on screen 2 |
| Tile grid heatmap (11) | NIFTY 50 / sector heatmap on screen 2; red tiles for rule hits and alerts |
| Connect sequence (12) | Market Open protocol: each check (broker, feed, collector, worker) appears as a link being established |
| Radial command ring (13) | Protocols and modes picked from a ring around the core |
| Hero + telemetry left + queue right (15) | Main screen layout during market hours |
| Time bands / globe (16) | Session clock and exchange status (Phase 9) |
| Red missing items in a tree (17) | Data completeness and job health view |
| Isometric system map (18) | Health Check protocol result as a live diagram |
| Table with TRUE/FALSE state column (8) | Health check: broker session, feed, collector, worker, kill switch, owner rules |

## Constraints (ours, not in the films)

- **Readability first:** prices and P&L at hero size with tabular digits; decorative text never
  carries data. The films' tiny unreadable text is decoration only.
- Every figure shown comes from a tool with its source and freshness (CLAUDE.md rule 5); demo data
  keeps its DEMO badge even in the HUD.
- Red is reserved for real danger so it keeps its meaning; amber for "watch this".
- Calm option: the same layout with glow and motion turned down. Image 18 shows how a calm, modern
  version of the same ideas looks; it is a good fallback if the film style hurts readability.
- Whether this becomes a theme next to the TradingView dark/light themes or replaces them is still
  open (plan §8, item 1).
