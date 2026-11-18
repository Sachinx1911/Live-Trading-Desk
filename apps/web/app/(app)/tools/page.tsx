"use client";

import { useMemo, useState } from "react";
import { Money, PanelCard } from "@/components/design";
import { HistoricalImport } from "@/components/tools/HistoricalImport";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { blackScholes, charges, type CalcProduct, type CalcSegment } from "@/lib/calculators";
import { formatNumber } from "@/lib/format";

const SEL = "h-8 border border-border bg-raised px-2 text-xs";

function Field({ id, label, value, onChange, step = "any" }: { id: string; label: string; value: string; onChange: (v: string) => void; step?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)} className="h-8 text-xs tabular" />
    </div>
  );
}

function ChargesCalculator() {
  const [segment, setSegment] = useState<CalcSegment>("equity");
  const [product, setProduct] = useState<CalcProduct>("intraday");
  const [qty, setQty] = useState("75");
  const [buy, setBuy] = useState("100");
  const [sell, setSell] = useState("101");
  const r = useMemo(() => charges(segment, product, Number(qty) || 0, Number(buy) || 0, Number(sell) || 0), [segment, product, qty, buy, sell]);
  const lines: [string, number][] = [
    ["Brokerage (₹20/order)", r.total.brokerage],
    ["STT", r.total.stt],
    ["Exchange txn", r.total.exchange],
    ["SEBI fee", r.total.sebi],
    ["Stamp duty (buy)", r.total.stamp],
    ["GST 18%", r.total.gst],
  ];
  return (
    <PanelCard title="Indian charges calculator" subtitle="Mirrors the backend StaticCostSchedule (rates effective 2025-10-01); round trip = one buy + one sell order">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="c-seg">Segment</Label>
            <select id="c-seg" value={segment} onChange={(e) => setSegment(e.target.value as CalcSegment)} className={SEL}>
              <option value="equity">equity</option>
              <option value="futures">futures</option>
              <option value="options">options (premium)</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="c-prod">Product</Label>
            <select id="c-prod" value={product} onChange={(e) => setProduct(e.target.value as CalcProduct)} className={SEL} disabled={segment !== "equity"}>
              <option value="intraday">intraday</option>
              <option value="delivery">delivery</option>
            </select>
          </div>
          <Field id="c-qty" label="Quantity" value={qty} onChange={setQty} step="1" />
          <Field id="c-buy" label="Buy price" value={buy} onChange={setBuy} />
          <Field id="c-sell" label="Sell price" value={sell} onChange={setSell} />
        </div>
        <table className="text-xs">
          <tbody>
            {lines.map(([k, v]) => (
              <tr key={k} className="border-b border-border/60"><td className="py-1 pr-4 text-text-2">{k}</td><td className="py-1 text-right"><Money value={v} muted /></td></tr>
            ))}
            <tr className="border-b border-border"><td className="py-1 pr-4 font-semibold">Total charges</td><td className="py-1 text-right font-semibold"><Money value={r.total.total} /></td></tr>
            <tr><td className="py-1 pr-4 text-text-2">Gross P&L</td><td className="py-1 text-right"><Money value={r.gross} signed /></td></tr>
            <tr><td className="py-1 pr-4 text-text-2">Net P&L</td><td className="py-1 text-right"><Money value={r.net} signed /></td></tr>
            <tr><td className="py-1 pr-4 text-text-2">Break-even move</td><td className="py-1 text-right tabular">{formatNumber(r.breakevenPoints, 2)} pts</td></tr>
          </tbody>
        </table>
      </div>
    </PanelCard>
  );
}

function GreeksCalculator() {
  const [spot, setSpot] = useState("24000");
  const [strike, setStrike] = useState("24000");
  const [days, setDays] = useState("7");
  const [iv, setIv] = useState("14");
  const [rate, setRate] = useState("6.5");
  const ce = blackScholes(Number(spot), Number(strike), Number(days), Number(iv), Number(rate), "CE");
  const pe = blackScholes(Number(spot), Number(strike), Number(days), Number(iv), Number(rate), "PE");
  const rows: [string, (g: NonNullable<typeof ce>) => string][] = [
    ["Price", (g) => formatNumber(g.price, 2)],
    ["Delta", (g) => g.delta.toFixed(4)],
    ["Gamma", (g) => g.gamma.toFixed(6)],
    ["Theta / day", (g) => g.theta.toFixed(2)],
    ["Vega / 1% IV", (g) => g.vega.toFixed(2)],
  ];
  return (
    <PanelCard title="Black–Scholes Greeks" subtitle="European pricing; NSE index options are European. Dividends ignored.">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="grid grid-cols-2 gap-2">
          <Field id="g-spot" label="Spot" value={spot} onChange={setSpot} />
          <Field id="g-strike" label="Strike" value={strike} onChange={setStrike} />
          <Field id="g-days" label="Days to expiry" value={days} onChange={setDays} />
          <Field id="g-iv" label="IV (%)" value={iv} onChange={setIv} />
          <Field id="g-rate" label="Rate (%)" value={rate} onChange={setRate} />
        </div>
        <table className="text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-text-3"><tr><th className="text-left font-medium"></th><th className="text-right font-medium">CE</th><th className="text-right font-medium">PE</th></tr></thead>
          <tbody>
            {rows.map(([k, f]) => (
              <tr key={k} className="border-b border-border/60"><td className="py-1 pr-4 text-text-2">{k}</td><td className="py-1 text-right tabular">{ce ? f(ce) : "—"}</td><td className="py-1 text-right tabular">{pe ? f(pe) : "—"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </PanelCard>
  );
}

export default function ToolsPage() {
  return (
    <div className="flex flex-col gap-3">
      <ChargesCalculator />
      <GreeksCalculator />
      <HistoricalImport />
    </div>
  );
}
