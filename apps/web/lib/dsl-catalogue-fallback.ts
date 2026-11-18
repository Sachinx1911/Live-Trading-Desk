/**
 * Fallback catalogue for the visual builder, copied from the Python DSL schema
 * (packages/strategy/src/strategy/dsl/schema.py) and indicator library defaults.
 * Used when `GET /strategies/dsl/catalogue` is unavailable; the API wins when present.
 */
import type { DslCatalogue, DslIndicatorSpec, DslParamSpec } from "./api/generated";

const int = (name: string, def: number, min = 1, max = 500): DslParamSpec => ({ name, type: "int", default: def, min, max });
const num = (name: string, def: number, min = 0, max = 100): DslParamSpec => ({ name, type: "float", default: def, min, max });

export const FALLBACK_INDICATORS: DslIndicatorSpec[] = [
  { type: "EMA", label: "EMA — exponential moving average", params: [int("period", 20)], outputs: ["value"] },
  { type: "SMA", label: "SMA — simple moving average", params: [int("period", 20)], outputs: ["value"] },
  { type: "RSI", label: "RSI (Wilder)", params: [int("period", 14)], outputs: ["value"] },
  { type: "ATR", label: "ATR (Wilder)", params: [int("period", 14)], outputs: ["value"] },
  { type: "VWAP", label: "VWAP with 1σ/2σ bands", params: [{ name: "anchor", type: "enum", default: "session", options: ["session"] }], outputs: ["value", "upper_1", "lower_1", "upper_2", "lower_2"] },
  { type: "SUPERTREND", label: "Supertrend", params: [int("period", 10), num("multiplier", 3, 0.5, 10)], outputs: ["value", "direction"] },
  { type: "BOLLINGER", label: "Bollinger bands", params: [int("period", 20), num("std", 2, 0.5, 5)], outputs: ["upper", "middle", "lower", "width"] },
  { type: "ADX", label: "ADX with +DI / −DI", params: [int("period", 14)], outputs: ["value", "plus_di", "minus_di"] },
  { type: "MACD", label: "MACD", params: [int("fast", 12), int("slow", 26), int("signal", 9)], outputs: ["macd", "signal", "hist"] },
  { type: "VOLUME_SMA", label: "Volume SMA", params: [int("period", 20)], outputs: ["value"] },
  { type: "PREV_DAY", label: "Previous day high / low / close", params: [], outputs: ["high", "low", "close"] },
  { type: "OPENING_RANGE", label: "Opening range", params: [int("minutes", 15, 1, 120)], outputs: ["high", "low"] },
  { type: "OI_CHANGE", label: "Open-interest change", params: [int("lookback_bars", 1, 1, 100)], outputs: ["value", "pct"] },
  { type: "SWING", label: "Swing high / low", params: [int("left", 5, 1, 50), int("right", 5, 1, 50)], outputs: ["last_high", "last_low"] },
  { type: "DAILY_TREND", label: "Daily trend label (up/down/flat)", params: [int("fast", 20), int("slow", 50)], outputs: ["label"] },
];

export const FALLBACK_CATALOGUE: DslCatalogue = {
  indicators: FALLBACK_INDICATORS,
  condition_kinds: ["compare", "cross", "between", "slope", "label", "group", "not"],
  price_fields: ["open", "high", "low", "close", "volume", "oi"],
  compare_ops: ["gt", "gte", "lt", "lte", "eq"],
  cross_directions: ["crosses_above", "crosses_below"],
  level_units: ["points", "percent", "atr", "structure", "indicator"],
  structure_levels: ["swing_low", "swing_high", "prev_day_low", "prev_day_high", "opening_range_low", "opening_range_high"],
  sizing_methods: ["fixed_lots", "fixed_quantity", "fixed_capital", "risk_percent"],
  products: ["INTRADAY", "DELIVERY", "CARRY_FORWARD"],
  directions: ["long_only", "short_only", "both"],
  timeframes: ["1m", "3m", "5m", "15m", "30m", "1h", "1d", "1w"],
  universe_kinds: ["instrument", "underlying_future", "underlying_option", "watchlist", "scanner"],
  contract_expiries: ["current_week", "next_week", "current_month", "next_month"],
  contract_strikes: ["ATM", "ITM1", "ITM2", "OTM1", "OTM2", "OTM3"],
};

export const CONTRACT_OPTION_TYPES = ["CE", "PE"] as const;
export const TRAIL_MODES = ["atr", "percent", "points", "indicator", "swing"] as const;
export const SLOPE_DIRECTIONS = ["rising", "falling"] as const;
export const ARITH_OPS = ["+", "-", "*", "/"] as const;
export const REGIME_SOURCES = ["vix", "adx", "daily_trend", "regime_label"] as const;
export const TIME_FILTER_MODES = ["allow_entries", "block_entries"] as const;
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

export const OP_LABEL: Record<string, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
};
