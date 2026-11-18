import type { ImportMapping, Timeframe } from "@/lib/api/generated";

export const IMPORT_TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"];

export const DEFAULT_MAPPING: ImportMapping = {
  exchange: "NSE",
  timeframe: "1d",
  symbol: "",
  symbol_column: null,
  ts_column: "date",
  ts_format: null,
  timezone: "Asia/Kolkata",
  open_column: "open",
  high_column: "high",
  low_column: "low",
  close_column: "close",
  volume_column: "volume",
  oi_column: null,
  source_label: null,
};

/** Reads the first line of a CSV/TXT file and returns its header cells (client-side only). */
export async function readCsvHeader(file: File): Promise<string[]> {
  const text = await file.slice(0, 64 * 1024).text();
  const line = text.split(/\r?\n/, 1)[0] ?? "";
  const sep = [",", ";", "\t", "|"].reduce((best, s) => (line.split(s).length > line.split(best).length ? s : best), ",");
  return line
    .split(sep)
    .map((c) => c.trim().replace(/^["']|["']$/g, "").replace(/^﻿/, ""))
    .filter((c) => c.length > 0);
}

const ALIASES: Record<string, string[]> = {
  ts: ["ts", "date", "datetime", "timestamp", "time", "dt", "trade_date"],
  open: ["open", "o", "open_price"],
  high: ["high", "h", "high_price"],
  low: ["low", "l", "low_price"],
  close: ["close", "c", "close_price", "adj_close", "last"],
  volume: ["volume", "vol", "v", "qty", "quantity"],
  oi: ["oi", "open_interest", "openinterest"],
  symbol: ["symbol", "ticker", "tradingsymbol", "instrument", "scrip", "name"],
};

function pick(columns: string[], key: keyof typeof ALIASES): string | null {
  const lower = columns.map((c) => c.toLowerCase());
  for (const alias of ALIASES[key]) {
    const i = lower.indexOf(alias);
    if (i >= 0) return columns[i];
  }
  return null;
}

/** Fills column fields from a header; keeps the user's non-column settings. */
export function autoMap(columns: string[], base: ImportMapping): ImportMapping {
  const symbolCol = pick(columns, "symbol");
  return {
    ...base,
    ts_column: pick(columns, "ts") ?? base.ts_column,
    open_column: pick(columns, "open") ?? base.open_column,
    high_column: pick(columns, "high") ?? base.high_column,
    low_column: pick(columns, "low") ?? base.low_column,
    close_column: pick(columns, "close") ?? base.close_column,
    volume_column: pick(columns, "volume"),
    oi_column: pick(columns, "oi"),
    symbol_column: symbolCol,
    symbol: symbolCol ? "" : base.symbol,
  };
}

/** Removes empty optional strings so the API sees nulls, not "". */
export function normaliseMapping(m: ImportMapping): ImportMapping {
  const nz = (v: string | null | undefined) => (v && v.trim() ? v.trim() : null);
  return {
    ...m,
    exchange: m.exchange.trim() || "NSE",
    symbol: nz(m.symbol)?.toUpperCase() ?? null,
    symbol_column: nz(m.symbol_column),
    ts_format: nz(m.ts_format),
    volume_column: nz(m.volume_column),
    oi_column: nz(m.oi_column),
    source_label: nz(m.source_label),
    timezone: m.timezone.trim() || "Asia/Kolkata",
  };
}

/** Client-side check before the dry run; mirrors the server's required fields. */
export function mappingProblems(m: ImportMapping): string[] {
  const out: string[] = [];
  if (!m.symbol && !m.symbol_column) out.push("Give a symbol or a symbol column.");
  for (const [k, label] of [
    ["ts_column", "Timestamp"],
    ["open_column", "Open"],
    ["high_column", "High"],
    ["low_column", "Low"],
    ["close_column", "Close"],
  ] as const) {
    if (!m[k]?.trim()) out.push(`${label} column is required.`);
  }
  return out;
}
