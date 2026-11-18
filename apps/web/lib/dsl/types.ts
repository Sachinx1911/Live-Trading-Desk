/**
 * Client-side mirror of the Strategy DSL v1 (packages/strategy/src/strategy/dsl/schema.py).
 * The visual builder edits a `DslDoc` directly so the JSON shown in the right rail is the
 * exact document that is validated and saved — no second model to keep in sync.
 */

export type IndicatorRef = { kind: "indicator"; id: string; field?: string; offset?: number };
export type PriceRef = { kind: "price"; field: string; offset?: number };
export type ConstRef = { kind: "const"; value: number };
export type ArithRef = { kind: "arith"; op: "+" | "-" | "*" | "/"; left: Operand; right: Operand };
export type Operand = IndicatorRef | PriceRef | ConstRef | ArithRef;

export type CompareCond = { kind: "compare"; left: Operand; op: string; right: Operand };
export type CrossCond = { kind: "cross"; left: Operand; direction: string; right: Operand };
export type BetweenCond = { kind: "between"; value: Operand; low: Operand; high: Operand };
export type SlopeCond = { kind: "slope"; value: Operand; direction: "rising" | "falling"; bars: number; strict?: boolean };
export type LabelCond = { kind: "label"; value: IndicatorRef; equals: string | number };
export type GroupCond = { kind: "group"; op: "and" | "or"; conditions: Condition[] };
export type NotCond = { kind: "not"; condition: Condition };
export type Condition = CompareCond | CrossCond | BetweenCond | SlopeCond | LabelCond | GroupCond | NotCond;

export type LevelSpec = {
  unit: string;
  value?: number | null;
  atr_indicator_id?: string | null;
  structure?: string | null;
  structure_indicator_id?: string | null;
  indicator_ref?: IndicatorRef | null;
  buffer_points?: number;
};
export type PartialTarget = { at: LevelSpec; close_pct: number; move_stop_to_breakeven?: boolean };
export type TargetSpec = Omit<LevelSpec, "unit"> & { unit?: string | null; rr_multiple?: number | null; partial?: PartialTarget[] };
export type TrailingSpec = { mode: string; value?: number | null; atr_indicator_id?: string | null; indicator_ref?: IndicatorRef | null; activate_after?: LevelSpec | null };

export type IndicatorSpec = { type: string; params: Record<string, number | string>; source?: string; timeframe?: string | null };
export type ContractSelector = { expiry: string; option_type?: string | null; strike?: string | null; roll_days_before_expiry?: number };
export type Universe = { kind: string; instrument_ids: string[]; underlying?: string | null; contract?: ContractSelector | null; watchlist_id?: string | null; scanner_id?: string | null };
export type SessionRules = {
  product: string;
  trade_start?: string | null;
  no_new_entries_after?: string | null;
  square_off_at?: string | null;
  skip_first_minutes?: number;
  trade_on_expiry_day?: boolean;
  allowed_weekdays?: number[];
};
export type RegimeFilter = { source: string; min?: number | null; max?: number | null; indicator_id?: string | null; allowed?: string[] | null };
export type TimeFilter = { start: string; end: string; mode: string };
export type EntryRules = { long?: Condition | null; short?: Condition | null; confirm_bars?: number; cooldown_bars?: number; one_entry_per_signal?: boolean };
export type ExitRules = { long?: Condition | null; short?: Condition | null; time_exit_bars?: number | null; exit_on_opposite_signal?: boolean };
export type PositionSizing = { method: string; lots?: number | null; quantity?: number | null; capital?: number | null; risk_percent?: number | null; max_lots?: number | null; max_capital_pct?: number | null };
export type FillPreferences = { entry_order_type: string; limit_offset_points?: number; limit_timeout_bars?: number; stop_order_type: string };

export interface DslDoc {
  dsl_schema_version: "1.0";
  name: string;
  description?: string | null;
  origin: string;
  original_text?: string | null;
  language?: string | null;
  market: string;
  universe: Universe;
  timeframe: string;
  context_timeframes: string[];
  session: SessionRules;
  regime_filters: RegimeFilter[];
  time_filters: TimeFilter[];
  indicators: Record<string, IndicatorSpec>;
  entry?: EntryRules | null;
  exit?: ExitRules | null;
  stop_loss?: LevelSpec | null;
  target?: TargetSpec | null;
  trailing?: TrailingSpec | null;
  position_sizing?: PositionSizing | null;
  max_positions: number;
  max_trades_per_day?: number | null;
  direction: string;
  fill: FillPreferences;
  metadata: Record<string, unknown>;
}

export function emptyDoc(): DslDoc {
  return {
    dsl_schema_version: "1.0",
    name: "",
    description: null,
    origin: "user_visual",
    market: "NSE",
    universe: { kind: "underlying_future", instrument_ids: [], underlying: "NIFTY", contract: { expiry: "current_month", roll_days_before_expiry: 1 } },
    timeframe: "5m",
    context_timeframes: [],
    session: { product: "INTRADAY", trade_start: "09:20", no_new_entries_after: "14:45", square_off_at: "15:15", skip_first_minutes: 0, trade_on_expiry_day: true, allowed_weekdays: [0, 1, 2, 3, 4] },
    regime_filters: [],
    time_filters: [],
    indicators: {},
    entry: { long: null, short: null, confirm_bars: 0, cooldown_bars: 0, one_entry_per_signal: true },
    exit: { long: null, short: null, time_exit_bars: null, exit_on_opposite_signal: false },
    stop_loss: { unit: "percent", value: 0.5, buffer_points: 0 },
    target: { unit: "percent", value: 1, buffer_points: 0, partial: [] },
    trailing: null,
    position_sizing: { method: "fixed_lots", lots: 1, max_lots: 1 },
    max_positions: 1,
    max_trades_per_day: 3,
    direction: "long_only",
    fill: { entry_order_type: "MARKET", limit_offset_points: 0, limit_timeout_bars: 1, stop_order_type: "SL_MARKET" },
    metadata: {},
  };
}

/** Coerce an arbitrary stored document into the shape the form expects (missing sections get defaults). */
export function coerceDoc(raw: Record<string, unknown>): DslDoc {
  const base = emptyDoc();
  const d = { ...base, ...(raw as Partial<DslDoc>) } as DslDoc;
  d.dsl_schema_version = "1.0";
  d.universe = { ...base.universe, ...(d.universe ?? {}) };
  d.session = { ...base.session, ...(d.session ?? {}) };
  d.fill = { ...base.fill, ...(d.fill ?? {}) };
  d.context_timeframes = Array.isArray(d.context_timeframes) ? d.context_timeframes : [];
  d.regime_filters = Array.isArray(d.regime_filters) ? d.regime_filters : [];
  d.time_filters = Array.isArray(d.time_filters) ? d.time_filters : [];
  d.indicators = d.indicators && typeof d.indicators === "object" ? d.indicators : {};
  d.metadata = d.metadata && typeof d.metadata === "object" ? d.metadata : {};
  if (!d.origin) d.origin = "user_visual";
  return d;
}

export function defaultOperand(kind: Operand["kind"], indicatorIds: string[]): Operand {
  switch (kind) {
    case "indicator":
      return { kind: "indicator", id: indicatorIds[0] ?? "", field: "value", offset: 0 };
    case "price":
      return { kind: "price", field: "close", offset: 0 };
    case "const":
      return { kind: "const", value: 0 };
    case "arith":
      return { kind: "arith", op: "*", left: { kind: "price", field: "close", offset: 0 }, right: { kind: "const", value: 1 } };
  }
}

export function defaultCondition(kind: Condition["kind"], indicatorIds: string[]): Condition {
  const ind = () => defaultOperand("indicator", indicatorIds);
  switch (kind) {
    case "compare":
      return { kind: "compare", left: ind(), op: "gt", right: { kind: "const", value: 0 } };
    case "cross":
      return { kind: "cross", left: ind(), direction: "crosses_above", right: ind() };
    case "between":
      return { kind: "between", value: ind(), low: { kind: "const", value: 0 }, high: { kind: "const", value: 100 } };
    case "slope":
      return { kind: "slope", value: ind(), direction: "rising", bars: 3, strict: false };
    case "label":
      return { kind: "label", value: { kind: "indicator", id: indicatorIds[0] ?? "", field: "label", offset: 0 }, equals: "up" };
    case "group":
      return { kind: "group", op: "and", conditions: [] };
    case "not":
      return { kind: "not", condition: { kind: "compare", left: ind(), op: "gt", right: { kind: "const", value: 0 } } };
  }
}

const OPS: Record<string, string> = { gt: ">", gte: "≥", lt: "<", lte: "≤", eq: "=", crosses_above: "crosses above", crosses_below: "crosses below" };

export function operandText(o: Operand): string {
  switch (o.kind) {
    case "indicator": {
      const f = o.field && o.field !== "value" ? `.${o.field}` : "";
      const off = o.offset ? `[${o.offset}]` : "";
      return `${o.id || "?"}${f}${off}`;
    }
    case "price":
      return o.offset ? `${o.field}[${o.offset}]` : o.field;
    case "const":
      return String(o.value);
    case "arith":
      return `(${operandText(o.left)} ${o.op} ${operandText(o.right)})`;
  }
}

export function conditionText(c: Condition | null | undefined): string {
  if (!c) return "—";
  switch (c.kind) {
    case "compare":
      return `${operandText(c.left)} ${OPS[c.op] ?? c.op} ${operandText(c.right)}`;
    case "cross":
      return `${operandText(c.left)} ${OPS[c.direction] ?? c.direction} ${operandText(c.right)}`;
    case "between":
      return `${operandText(c.value)} between ${operandText(c.low)} and ${operandText(c.high)}`;
    case "slope":
      return `${operandText(c.value)} ${c.direction} for ${c.bars} bars`;
    case "label":
      return `${operandText(c.value)} is "${c.equals}"`;
    case "group":
      return c.conditions.length ? `(${c.conditions.map(conditionText).join(` ${c.op.toUpperCase()} `)})` : "(empty group)";
    case "not":
      return `NOT ${conditionText(c.condition)}`;
  }
}

/** Indicator ids referenced anywhere in a condition tree. */
export function referencedIndicators(c: Condition | null | undefined, acc = new Set<string>()): Set<string> {
  if (!c) return acc;
  const op = (o: Operand) => {
    if (o.kind === "indicator") acc.add(o.id);
    if (o.kind === "arith") { op(o.left); op(o.right); }
  };
  switch (c.kind) {
    case "compare": case "cross": op(c.left); op(c.right); break;
    case "between": op(c.value); op(c.low); op(c.high); break;
    case "slope": op(c.value); break;
    case "label": op(c.value); break;
    case "group": c.conditions.forEach((x) => referencedIndicators(x, acc)); break;
    case "not": referencedIndicators(c.condition, acc); break;
  }
  return acc;
}

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Fast client-side checks mirroring the most common server errors; the server remains the authority. */
export function clientValidate(d: DslDoc): string[] {
  const errs: string[] = [];
  if (!d.name.trim()) errs.push("Name is required.");
  if (d.name.length > 80) errs.push("Name must be 80 characters or fewer.");
  if (d.universe.kind === "instrument" && d.universe.instrument_ids.length === 0) errs.push("Universe: pick at least one instrument.");
  if ((d.universe.kind === "underlying_future" || d.universe.kind === "underlying_option") && !d.universe.underlying) errs.push("Universe: underlying symbol is required.");
  if (d.universe.kind === "underlying_option" && !d.universe.contract?.option_type) errs.push("Universe: option type (CE/PE) is required for options.");
  if (d.universe.kind === "watchlist" && !d.universe.watchlist_id) errs.push("Universe: watchlist id is required.");
  if (d.universe.kind === "scanner" && !d.universe.scanner_id) errs.push("Universe: scanner id is required.");
  if (d.context_timeframes.length > 2) errs.push("At most 2 context timeframes.");
  for (const [k, v] of Object.entries({ trade_start: d.session.trade_start, no_new_entries_after: d.session.no_new_entries_after, square_off_at: d.session.square_off_at })) {
    if (v && !TIME_RE.test(v)) errs.push(`Session: ${k} must be HH:MM.`);
  }
  for (const [i, t] of d.time_filters.entries()) {
    if (!TIME_RE.test(t.start) || !TIME_RE.test(t.end)) errs.push(`Time filter ${i + 1}: start/end must be HH:MM.`);
  }
  const ids = Object.keys(d.indicators);
  for (const id of ids) {
    if (!/^[a-z][a-z0-9_]*$/.test(id)) errs.push(`Indicator id "${id}" must be lowercase letters, digits and underscores.`);
    if (!d.indicators[id].type) errs.push(`Indicator "${id}" has no type.`);
  }
  const wantLong = d.direction !== "short_only";
  const wantShort = d.direction !== "long_only";
  if (wantLong && !d.entry?.long) errs.push("Entry: a long entry condition is required for this direction.");
  if (wantShort && !d.entry?.short) errs.push("Entry: a short entry condition is required for this direction.");
  const checkTree = (c: Condition | null | undefined, where: string) => {
    if (!c) return;
    const walk = (x: Condition) => {
      if (x.kind === "group") {
        if (x.conditions.length === 0) errs.push(`${where}: a group has no conditions.`);
        if (x.conditions.length > 10) errs.push(`${where}: a group has more than 10 conditions.`);
        x.conditions.forEach(walk);
      } else if (x.kind === "not") walk(x.condition);
      else if (x.kind === "slope" && x.bars < 1) errs.push(`${where}: slope bars must be ≥ 1.`);
    };
    walk(c);
    for (const id of referencedIndicators(c)) if (!ids.includes(id)) errs.push(`${where}: references unknown indicator "${id || "(blank)"}".`);
  };
  checkTree(d.entry?.long, "Entry long");
  checkTree(d.entry?.short, "Entry short");
  checkTree(d.exit?.long, "Exit long");
  checkTree(d.exit?.short, "Exit short");
  const checkLevel = (l: LevelSpec | TargetSpec | null | undefined, where: string) => {
    if (!l) return;
    const unit = l.unit ?? null;
    if (unit === "atr" && !l.atr_indicator_id) errs.push(`${where}: ATR unit needs an ATR indicator id.`);
    if (unit === "atr" && l.atr_indicator_id && !ids.includes(l.atr_indicator_id)) errs.push(`${where}: ATR indicator "${l.atr_indicator_id}" is not defined.`);
    if (unit === "structure" && !l.structure) errs.push(`${where}: structure unit needs a structure level.`);
    if (unit === "indicator" && !l.indicator_ref?.id) errs.push(`${where}: indicator unit needs an indicator reference.`);
    if ((unit === "points" || unit === "percent" || unit === "atr") && (l.value == null || l.value <= 0)) errs.push(`${where}: value must be > 0.`);
  };
  checkLevel(d.stop_loss, "Stop loss");
  if (d.target) {
    if (d.target.unit) checkLevel(d.target, "Target");
    else if (d.target.rr_multiple == null) errs.push("Target: choose a unit or a risk:reward multiple.");
    for (const [i, p] of (d.target.partial ?? []).entries()) {
      checkLevel(p.at, `Partial target ${i + 1}`);
      if (!(p.close_pct > 0 && p.close_pct <= 100)) errs.push(`Partial target ${i + 1}: close % must be in (0, 100].`);
    }
  }
  if (d.trailing) {
    if ((d.trailing.mode === "atr") && !d.trailing.atr_indicator_id) errs.push("Trailing: ATR mode needs an ATR indicator id.");
    if ((d.trailing.mode === "percent" || d.trailing.mode === "points" || d.trailing.mode === "atr") && !(d.trailing.value && d.trailing.value > 0)) errs.push("Trailing: value must be > 0.");
    if (d.trailing.mode === "indicator" && !d.trailing.indicator_ref?.id) errs.push("Trailing: indicator mode needs an indicator reference.");
  }
  const ps = d.position_sizing;
  if (ps) {
    const need: Record<string, keyof PositionSizing> = { fixed_lots: "lots", fixed_quantity: "quantity", fixed_capital: "capital", risk_percent: "risk_percent" };
    const f = need[ps.method];
    if (f && !(Number(ps[f]) > 0)) errs.push(`Position sizing: ${f.replace("_", " ")} must be > 0 for ${ps.method}.`);
  }
  if (d.max_positions < 1) errs.push("Max positions must be ≥ 1.");
  if (d.max_trades_per_day != null && d.max_trades_per_day < 1) errs.push("Max trades per day must be ≥ 1 (or blank).");
  return errs;
}

/** Strip null/undefined optional fields so the emitted JSON stays compact and `extra=forbid`-safe. */
export function cleanDoc(d: DslDoc): Record<string, unknown> {
  const strip = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(strip);
    if (v && typeof v === "object") {
      const out: Record<string, unknown> = {};
      for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
        if (x === undefined) continue;
        if (x === null && k !== "unit") continue;
        out[k] = strip(x);
      }
      return out;
    }
    return v;
  };
  return strip(d) as Record<string, unknown>;
}
