/**
 * Client-side calculators for /tools. Rates mirror backend StaticCostSchedule
 * (packages/execution/src/execution/costs.py, effective 2025-10-01). Keep both in sync.
 */

export type CalcSegment = "equity" | "futures" | "options";
export type CalcProduct = "intraday" | "delivery";

interface RateSet {
  stt: { rate: number; side: "buy" | "sell" | "both" };
  exchange: number; // both sides
  sebi: number; // both sides, 0.0001% = Rs 10 / crore
  stamp: number; // buy side only
}

const BROKERAGE_FLAT = 20; // Rs per executed order
const GST = 0.18; // on brokerage + exchange + SEBI

const RATES: Record<"delivery" | "intraday" | "futures" | "options", RateSet> = {
  delivery: { stt: { rate: 0.1 / 100, side: "both" }, exchange: 0.00297 / 100, sebi: 0.0001 / 100, stamp: 0.015 / 100 },
  intraday: { stt: { rate: 0.025 / 100, side: "sell" }, exchange: 0.00297 / 100, sebi: 0.0001 / 100, stamp: 0.003 / 100 },
  futures: { stt: { rate: 0.02 / 100, side: "sell" }, exchange: 0.00173 / 100, sebi: 0.0001 / 100, stamp: 0.002 / 100 },
  options: { stt: { rate: 0.1 / 100, side: "sell" }, exchange: 0.03503 / 100, sebi: 0.0001 / 100, stamp: 0.003 / 100 },
};

export interface ChargeLine {
  brokerage: number;
  stt: number;
  exchange: number;
  sebi: number;
  stamp: number;
  gst: number;
  total: number;
}

function leg(product: keyof typeof RATES, side: "buy" | "sell", notional: number): ChargeLine {
  const r = RATES[product];
  const brokerage = notional > 0 ? BROKERAGE_FLAT : 0;
  const stt = r.stt.side === "both" || r.stt.side === side ? notional * r.stt.rate : 0;
  const exchange = notional * r.exchange;
  const sebi = notional * r.sebi;
  const stamp = side === "buy" ? notional * r.stamp : 0;
  const gst = (brokerage + exchange + sebi) * GST;
  return { brokerage, stt, exchange, sebi, stamp, gst, total: brokerage + stt + exchange + sebi + stamp + gst };
}

export function charges(segment: CalcSegment, product: CalcProduct, qty: number, buyPrice: number, sellPrice: number) {
  const key: keyof typeof RATES = segment === "equity" ? product : segment;
  const buy = leg(key, "buy", qty * buyPrice);
  const sell = leg(key, "sell", qty * sellPrice);
  const total: ChargeLine = {
    brokerage: buy.brokerage + sell.brokerage,
    stt: buy.stt + sell.stt,
    exchange: buy.exchange + sell.exchange,
    sebi: buy.sebi + sell.sebi,
    stamp: buy.stamp + sell.stamp,
    gst: buy.gst + sell.gst,
    total: buy.total + sell.total,
  };
  const gross = qty * (sellPrice - buyPrice);
  const breakevenPoints = qty > 0 ? total.total / qty : 0;
  return { buy, sell, total, gross, net: gross - total.total, breakevenPoints };
}

// ---------------------------------------------------------------- Black–Scholes
function cdf(x: number): number {
  // Abramowitz-Stegun approximation of the standard normal CDF
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989422804014327 * Math.exp(-0.5 * x * x);
  const p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return x >= 0 ? 1 - p : p;
}
function pdf(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

export interface Greeks {
  price: number;
  delta: number;
  gamma: number;
  theta: number; // per day
  vega: number; // per 1% IV
}

export function blackScholes(spot: number, strike: number, days: number, ivPct: number, ratePct: number, type: "CE" | "PE"): Greeks | null {
  const t = days / 365;
  const iv = ivPct / 100;
  const r = ratePct / 100;
  if (spot <= 0 || strike <= 0 || t <= 0 || iv <= 0) return null;
  const d1 = (Math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * Math.sqrt(t));
  const d2 = d1 - iv * Math.sqrt(t);
  const disc = Math.exp(-r * t);
  const gamma = pdf(d1) / (spot * iv * Math.sqrt(t));
  const vega = (spot * pdf(d1) * Math.sqrt(t)) / 100;
  if (type === "CE") {
    const price = spot * cdf(d1) - strike * disc * cdf(d2);
    const theta = (-(spot * pdf(d1) * iv) / (2 * Math.sqrt(t)) - r * strike * disc * cdf(d2)) / 365;
    return { price, delta: cdf(d1), gamma, theta, vega };
  }
  const price = strike * disc * cdf(-d2) - spot * cdf(-d1);
  const theta = (-(spot * pdf(d1) * iv) / (2 * Math.sqrt(t)) + r * strike * disc * cdf(-d2)) / 365;
  return { price, delta: cdf(d1) - 1, gamma, theta, vega };
}
