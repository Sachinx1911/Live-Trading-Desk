/**
 * Panel registry (Mark 1 Stage 4.4, docs/panels.md).
 *
 * Every important screen is also a chrome-less, read-only PANEL with a stable URL under
 * `/panel/<id>`, so the owner's assistant (jarvis and its macOS wrapper) can open exactly that
 * view on whichever monitor it chooses. This module is the single source of truth for the
 * list: the panel pages validate their query string with `parsePanelParams`, the full pages
 * build their "Open as panel" links with `panelUrl`, and `/panel/registry.json` serves
 * `panelRegistry()` so jarvis can discover panels and their parameters.
 *
 * Shared by server (route handler) and client code: keep it free of React and browser APIs.
 * Panels never place orders, change rules, run protocols or touch the kill switch.
 */

export const PANEL_REGISTRY_VERSION = 1;

export type PanelParamType =
  | "symbol" // instrument symbol from the instrument master, e.g. NIFTY, RELIANCE
  | "symbols" // comma-separated symbols
  | "timeframe"
  | "date" // YYYY-MM-DD (IST trading day)
  | "time" // HH:MM (IST)
  | "boolean" // 1 / 0 (also true / false)
  | "integer"; // positive integer id

export interface PanelParam {
  name: string;
  type: PanelParamType;
  required: boolean;
  description: string;
  example: string;
  /** Value used when the parameter is omitted (documented, applied by the panel). */
  default?: string;
  /** Allowed values, when the set is closed. */
  values?: readonly string[];
}

export interface PanelDef {
  id: string;
  title: string;
  description: string;
  /** Path template with `{param}` placeholders, for humans; build URLs with `panelUrl`. */
  path: string;
  params: readonly PanelParam[];
  /** Full app page the panel's "open in app" link goes to. */
  fullPage: string;
  /** Sizing hints in CSS pixels; every panel works from 480×320 up to a full 4K screen. */
  size: { min: [number, number]; preferred: [number, number] };
  /** What the freshness badge in the panel header describes. */
  dataState: string;
}

/** Chart timeframes offered by the market page (the API stores more; these are the panel set). */
export const PANEL_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d"] as const;
export const MAX_QUOTE_SYMBOLS = 12;

const MIN: [number, number] = [480, 320];

export const PANELS = [
  {
    id: "chart",
    title: "Chart",
    description: "Candlestick chart of one instrument from stored candles, with the forming bar from live ticks when the feed is up.",
    path: "/panel/chart?symbol={symbol}&tf={tf}",
    params: [
      { name: "symbol", type: "symbol", required: true, description: "Instrument symbol (NSE).", example: "NIFTY" },
      { name: "tf", type: "timeframe", required: false, description: "Candle timeframe.", example: "5m", default: "5m", values: PANEL_TIMEFRAMES },
    ],
    fullPage: "/market",
    size: { min: MIN, preferred: [1280, 720] },
    dataState: "Quote freshness of the instrument; Historical when only stored candles are shown; Demo for the fake provider.",
  },
  {
    id: "option-chain",
    title: "Option chain",
    description: "Latest stored option-chain snapshot for an index, optionally with Gamma, Theta and Vega.",
    path: "/panel/option-chain?symbol={symbol}&expiry={expiry}&greeks={greeks}",
    params: [
      { name: "symbol", type: "symbol", required: true, description: "Underlying index.", example: "NIFTY", values: ["NIFTY", "BANKNIFTY"] },
      { name: "expiry", type: "date", required: false, description: "Expiry date; must be one of the stored expiries.", example: "2026-11-25", default: "nearest stored expiry" },
      { name: "greeks", type: "boolean", required: false, description: "Show Gamma, Theta and Vega columns.", example: "1", default: "0" },
    ],
    fullPage: "/market/option-chain",
    size: { min: MIN, preferred: [1100, 800] },
    dataState: "Freshness of the chain snapshot as reported by the API.",
  },
  {
    id: "oi-change",
    title: "OI change",
    description: "Per-strike call and put open-interest change between two times of one day, from stored chain snapshots.",
    path: "/panel/oi-change?symbol={symbol}&date={date}&from={from}&to={to}",
    params: [
      { name: "symbol", type: "symbol", required: true, description: "Underlying index.", example: "NIFTY", values: ["NIFTY", "BANKNIFTY"] },
      { name: "date", type: "date", required: false, description: "Trading day (IST).", example: "2026-11-20", default: "today (IST)" },
      { name: "from", type: "time", required: false, description: "Start time (IST).", example: "09:15", default: "09:15" },
      { name: "to", type: "time", required: false, description: "End time (IST); must be after `from`.", example: "15:30", default: "15:30" },
      { name: "expiry", type: "date", required: false, description: "Expiry; must be stored for that day.", example: "2026-11-25", default: "nearest expiry stored that day" },
      { name: "range", type: "integer", required: false, description: "Strikes each side of spot; 0 = all.", example: "10", default: "10" },
    ],
    fullPage: "/market/oi-change",
    size: { min: MIN, preferred: [1200, 640] },
    dataState: "Freshness of the snapshots used, as reported by the API.",
  },
  {
    id: "quotes",
    title: "Quotes",
    description: "Strip of quote tiles (last price, change, per-tile freshness) for a list of instruments.",
    path: "/panel/quotes?symbols={symbols}",
    params: [
      { name: "symbols", type: "symbols", required: true, description: `Comma-separated symbols, at most ${MAX_QUOTE_SYMBOLS}.`, example: "NIFTY,BANKNIFTY,INDIAVIX" },
    ],
    fullPage: "/market",
    size: { min: MIN, preferred: [960, 360] },
    dataState: "Market feed state; each tile also carries its own quote freshness.",
  },
  {
    id: "positions",
    title: "Positions",
    description: "Paper account equity, cash and P&L, with its open positions. Paper only; never live.",
    path: "/panel/positions?account={account}",
    params: [
      { name: "account", type: "integer", required: true, description: "Paper account id.", example: "1" },
      { name: "closed", type: "boolean", required: false, description: "Include closed positions.", example: "0", default: "0" },
    ],
    fullPage: "/paper/positions",
    size: { min: MIN, preferred: [1100, 520] },
    dataState: "Always Demo · paper: simulated fills. Live last prices are marked per row.",
  },
  {
    id: "alerts",
    title: "Alerts",
    description: "Stored alerts feed, newest first. Acknowledging stays in the app.",
    path: "/panel/alerts",
    params: [
      { name: "unread", type: "boolean", required: false, description: "Only unacknowledged alerts.", example: "1", default: "0" },
      { name: "limit", type: "integer", required: false, description: "How many alerts (1-300).", example: "50", default: "100" },
    ],
    fullPage: "/alerts",
    size: { min: MIN, preferred: [520, 800] },
    dataState: "Historical · stored records, with the market feed state alongside.",
  },
  {
    id: "breadth",
    title: "Market breadth",
    description: "NIFTY 50 breadth for the latest stored session plus the stored history.",
    path: "/panel/breadth",
    params: [],
    fullPage: "/dashboard",
    size: { min: MIN, preferred: [760, 560] },
    dataState: "Historical · end-of-day values with their as-of date.",
  },
  {
    id: "regime",
    title: "Regime",
    description: "Deterministic regime labels (trend, volatility, structure, day type, events); one index or all.",
    path: "/panel/regime?symbol={symbol}",
    params: [
      { name: "symbol", type: "symbol", required: false, description: "Index to show; omit for every tracked index.", example: "NIFTY" },
      { name: "days", type: "integer", required: false, description: "History cells to show (5-120).", example: "30", default: "30" },
    ],
    fullPage: "/dashboard",
    size: { min: MIN, preferred: [900, 360] },
    dataState: "Historical · computed by the worker, with the computed time.",
  },
  {
    id: "scanner",
    title: "Scanner",
    description: "Result of a scanner preset or saved scan over the end-of-day snapshot.",
    path: "/panel/scanner?preset={preset}",
    params: [{ name: "preset", type: "integer", required: true, description: "Preset or saved scan id (see /scanner).", example: "1" }],
    fullPage: "/scanner",
    size: { min: MIN, preferred: [1200, 760] },
    dataState: "Historical · EOD snapshot date and provider.",
  },
  {
    id: "backtest",
    title: "Backtest result",
    description: "Status banner, key metrics and the equity curve of one backtest job.",
    path: "/panel/backtest?job={job}",
    params: [{ name: "job", type: "integer", required: true, description: "Backtest job id.", example: "42" }],
    fullPage: "/backtesting/{job}",
    size: { min: MIN, preferred: [1100, 720] },
    dataState: "Historical · stored backtest result.",
  },
  {
    id: "brief",
    title: "Evening brief",
    description: "Stored end-of-day brief (indices, PCR, breadth, paper P&L, data completeness, next session).",
    path: "/panel/brief?date={date}",
    params: [{ name: "date", type: "date", required: false, description: "Report day.", example: "2026-11-20", default: "latest stored brief" }],
    fullPage: "/reports",
    size: { min: MIN, preferred: [1100, 760] },
    dataState: "Historical · stored record with its generation time.",
  },
  {
    id: "news",
    title: "News",
    description: "Stored RSS headlines, optionally only those naming a symbol. Links open the publisher.",
    path: "/panel/news?symbol={symbol}",
    params: [
      { name: "symbol", type: "symbol", required: false, description: "Only headlines tagged with this symbol.", example: "RELIANCE" },
      { name: "limit", type: "integer", required: false, description: "How many headlines (1-200).", example: "30", default: "50" },
    ],
    fullPage: "/news",
    size: { min: MIN, preferred: [560, 800] },
    dataState: "Historical · stored headlines with their published time.",
  },
  {
    id: "protocol-run",
    title: "Protocol run",
    description: "One protocol run with each step's stored result. Confirming or cancelling stays in the app.",
    path: "/panel/protocol-run?id={id}",
    params: [{ name: "id", type: "integer", required: true, description: "Protocol run id.", example: "7" }],
    fullPage: "/protocols",
    size: { min: MIN, preferred: [720, 720] },
    dataState: "Historical · stored run; refreshes while the run is open.",
  },
] as const satisfies readonly PanelDef[];

export type PanelId = (typeof PANELS)[number]["id"];

export function getPanel(id: PanelId): PanelDef {
  return PANELS.find((p) => p.id === id) as PanelDef;
}

/** Build a panel URL (path + query). Unknown or empty params are dropped; `base` makes it absolute. */
export function panelUrl(id: PanelId, params: Record<string, string | number | boolean | null | undefined> = {}, base?: string): string {
  const def = getPanel(id);
  const parts: string[] = [];
  for (const p of def.params) {
    const v = params[p.name];
    if (v == null || v === "") continue;
    const s = typeof v === "boolean" ? (v ? "1" : "0") : String(v);
    // ":" and "," are legal in a query; keep times and symbol lists readable (09:15, NIFTY,BANKNIFTY).
    parts.push(`${p.name}=${encodeURIComponent(s).replace(/%3A/gi, ":").replace(/%2C/gi, ",")}`);
  }
  const qs = parts.join("&");
  const path = `/panel/${id}${qs ? `?${qs}` : ""}`;
  return base ? `${base.replace(/\/$/, "")}${path}` : path;
}

/** Full-page URL for the "open in app" link (fills `{param}` placeholders). */
export function fullPageUrl(id: PanelId, values: Record<string, string | undefined> = {}): string {
  return getPanel(id).fullPage.replace(/\{(\w+)\}/g, (_, k: string) => encodeURIComponent(values[k] ?? ""));
}

// ----------------------------------------------------------------------- validation

export interface PanelParamError {
  param: string;
  message: string;
}

export type ParsedParams = Record<string, string | undefined>;

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const SYMBOL_RE = /^[A-Z0-9][A-Z0-9&_.-]{0,39}$/;

function validDate(v: string): boolean {
  if (!DATE_RE.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}

function checkOne(p: PanelParam, raw: string): { value?: string; error?: string } {
  const v = raw.trim();
  switch (p.type) {
    case "symbol": {
      const s = v.toUpperCase();
      if (!SYMBOL_RE.test(s)) return { error: `"${raw}" is not a valid symbol (letters, digits, & - _ .)` };
      if (p.values && !p.values.includes(s)) return { error: `"${s}" is not supported here; use one of ${p.values.join(", ")}` };
      return { value: s };
    }
    case "symbols": {
      const list = v.split(",").map((x) => x.trim().toUpperCase()).filter(Boolean);
      if (list.length === 0) return { error: "no symbols given" };
      if (list.length > MAX_QUOTE_SYMBOLS) return { error: `${list.length} symbols given; at most ${MAX_QUOTE_SYMBOLS}` };
      const bad = list.find((s) => !SYMBOL_RE.test(s));
      if (bad) return { error: `"${bad}" is not a valid symbol` };
      return { value: [...new Set(list)].join(",") };
    }
    case "timeframe":
      return p.values?.includes(v) ? { value: v } : { error: `"${raw}" is not a timeframe; use one of ${p.values?.join(", ")}` };
    case "date":
      return validDate(v) ? { value: v } : { error: `"${raw}" is not a date in YYYY-MM-DD form` };
    case "time":
      return TIME_RE.test(v) ? { value: v } : { error: `"${raw}" is not a time in HH:MM form (24 h, IST)` };
    case "boolean":
      if (["1", "true", "yes"].includes(v.toLowerCase())) return { value: "1" };
      if (["0", "false", "no"].includes(v.toLowerCase())) return { value: "0" };
      return { error: `"${raw}" is not 1 or 0` };
    case "integer":
      return /^\d{1,9}$/.test(v) ? { value: String(Number(v)) } : { error: `"${raw}" is not a whole number` };
  }
}

/**
 * Validate a panel's query string against its registry entry. Missing required params and
 * malformed values become errors naming the parameter; unknown params are ignored.
 * Defaults are NOT filled in here (panels apply them, some are dynamic such as "today").
 */
export function parsePanelParams(id: PanelId, search: URLSearchParams): { values: ParsedParams; errors: PanelParamError[] } {
  const def = getPanel(id);
  const values: ParsedParams = {};
  const errors: PanelParamError[] = [];
  for (const p of def.params) {
    const raw = search.get(p.name);
    if (raw == null || raw.trim() === "") {
      if (p.required) errors.push({ param: p.name, message: `required (${p.description.replace(/\.$/, "")}, e.g. ${p.name}=${p.example})` });
      continue;
    }
    const r = checkOne(p, raw);
    if (r.error) errors.push({ param: p.name, message: r.error });
    else values[p.name] = r.value;
  }
  return { values, errors };
}

/** JSON document served at /panel/registry.json. */
export function panelRegistry() {
  return {
    version: PANEL_REGISTRY_VERSION,
    description:
      "Read-only panels of the trading platform web app. Open `path` (with query params) relative to the web app origin. Panels never place orders, change rules, run protocols or touch the kill switch.",
    auth: "Panels use the web app's own session (browser storage); an unauthenticated window falls back to the app login, then returns to the panel.",
    panels: PANELS.map((p) => ({
      id: p.id,
      title: p.title,
      description: p.description,
      path: `/panel/${p.id}`,
      template: p.path,
      example: panelUrl(p.id, Object.fromEntries(p.params.map((x) => [x.name, x.example]))),
      params: p.params,
      full_page: p.fullPage,
      size: { min_width: p.size.min[0], min_height: p.size.min[1], preferred_width: p.size.preferred[0], preferred_height: p.size.preferred[1] },
      data_state: p.dataState,
    })),
  };
}
