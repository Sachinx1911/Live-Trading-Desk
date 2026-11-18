import type { SavedScan, ScanCondition, ScanField, ScanFilters, ScanOp, ScanSort } from "@/lib/api/generated";
import { formatNumber } from "@/lib/format";

/** Column sets mirror TradingView's screener tabs; "custom" is whatever the user picked. */
export const COLUMN_SETS: Record<string, { label: string; columns: string[] }> = {
  overview: {
    label: "Overview",
    columns: ["symbol", "name", "segment", "last_close", "change_1d_pct", "volume", "rel_volume", "rsi14", "adx14", "atr14_pct", "ema_alignment", "regime_trend"],
  },
  performance: {
    label: "Performance",
    columns: ["symbol", "name", "last_close", "change_1d_pct", "change_5d_pct", "change_20d_pct", "gap_pct", "dist_52w_high_pct", "dist_52w_low_pct", "rel_volume"],
  },
  technicals: {
    label: "Technicals",
    columns: ["symbol", "name", "last_close", "rsi14", "adx14", "atr14_pct", "ema20", "ema50", "ema200", "ema_alignment", "regime_trend", "regime_volatility"],
  },
  derivatives: {
    label: "Derivatives",
    columns: ["symbol", "name", "underlying", "expiry", "lot_size", "last_close", "change_1d_pct", "oi", "oi_change_1d_pct", "volume", "rel_volume"],
  },
};
export const COLUMN_SET_IDS = [...Object.keys(COLUMN_SETS), "custom"] as const;

export const OP_LABEL: Record<ScanOp, string> = {
  eq: "=", ne: "≠", gt: ">", gte: "≥", lt: "<", lte: "≤", between: "between", in: "in", contains: "contains",
};

export function opsForType(t: ScanField["type"]): ScanOp[] {
  switch (t) {
    case "number":
    case "percent":
      return ["gt", "gte", "lt", "lte", "between", "eq", "ne"];
    case "date":
      return ["eq", "gt", "gte", "lt", "lte", "between"];
    case "enum":
      return ["in", "eq", "ne"];
    case "bool":
      return ["eq"];
    default:
      return ["contains", "eq", "ne", "in"];
  }
}

export function defaultOp(t: ScanField["type"]): ScanOp {
  return opsForType(t)[0];
}

function fmtVal(f: ScanField | undefined, v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return v.map((x) => fmtVal(f, x)).join(", ");
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return f?.type === "percent" ? `${formatNumber(v, 2)}%` : formatNumber(v, Number.isInteger(v) ? 0 : 2);
  return String(v);
}

export function conditionLabel(c: ScanCondition, f: ScanField | undefined): string {
  const name = f?.label ?? c.field;
  if (c.op === "between" && Array.isArray(c.value)) return `${name} ${fmtVal(f, c.value[0])} – ${fmtVal(f, c.value[1])}`;
  return `${name} ${OP_LABEL[c.op]} ${fmtVal(f, c.value)}`;
}

export const EMPTY_FILTERS: ScanFilters = { all: [], any: [] };

export function sameFilters(a: ScanFilters, b: ScanFilters): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function sameScan(a: { filters: ScanFilters; sort: ScanSort | null; columns: string[] }, s: SavedScan): boolean {
  return sameFilters(a.filters, s.filters) && JSON.stringify(a.sort ?? null) === JSON.stringify(s.sort ?? null) && a.columns.join() === s.columns.join();
}

/** Which column-set tab matches these columns, else "custom". */
export function columnSetFor(columns: string[]): string {
  const key = columns.join();
  for (const [id, set] of Object.entries(COLUMN_SETS)) if (set.columns.join() === key) return id;
  return "custom";
}
