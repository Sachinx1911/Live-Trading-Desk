"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { InstrumentSearch, instrumentLabel } from "@/components/market/InstrumentSearch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateBacktest } from "@/lib/api/backtests";
import { ApiRequestError } from "@/lib/api/client";
import type { FillMode, Instrument, SlippageModel, StrategyVersion, Timeframe } from "@/lib/api/generated";
import { StrategyVersionPicker } from "./StrategyVersionPicker";

const SEL = "h-8 border border-border bg-raised px-2 text-xs";
const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1h", "1d"];

export function isoDay(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function BacktestForm({ presetVersionId, presetStrategyId }: { presetVersionId?: number; presetStrategyId?: number }) {
  const router = useRouter();
  const create = useCreateBacktest();
  const [strategyId, setStrategyId] = useState<number | null>(presetStrategyId ?? null);
  const [version, setVersion] = useState<StrategyVersion | null>(null);
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const today = new Date();
  const yearAgo = new Date(today.getTime() - 365 * 86400_000);
  const [start, setStart] = useState(isoDay(yearAgo));
  const [end, setEnd] = useState(isoDay(today));
  const [timeframe, setTimeframe] = useState<Timeframe | "">("");
  const [capital, setCapital] = useState("100000");
  const [slipModel, setSlipModel] = useState<SlippageModel>("spread_aware");
  const [bps, setBps] = useState("2");
  const [fillMode, setFillMode] = useState<FillMode>("next_bar_open");
  const [seed, setSeed] = useState("42");
  const [label, setLabel] = useState("");
  const err = create.error instanceof ApiRequestError ? create.error.message : create.error ? "Cannot reach the API." : null;
  const dslTf = version ? String((version.dsl as { timeframe?: string }).timeframe ?? "") : "";
  const chosenVersionId = version?.id ?? presetVersionId ?? null;

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!chosenVersionId || !instrument) return;
        const job = await create.mutateAsync({
          strategy_version_id: chosenVersionId,
          instrument_id: instrument.instrument_id,
          start,
          end,
          timeframe: timeframe || null,
          initial_capital: capital,
          seed: Number(seed) || 42,
          fill_mode: fillMode,
          slippage: { model: slipModel, bps: Number(bps) || 0, size_impact: 0.5 },
          label: label || null,
        });
        router.push(`/backtesting/${job.id}`);
      }}
    >
      <StrategyVersionPicker strategyId={strategyId} versionId={chosenVersionId} onStrategy={setStrategyId} onVersion={setVersion} idPrefix="bt" />
      <div className="flex flex-col gap-1.5">
        <Label>Instrument</Label>
        {instrument ? (
          <div className="flex items-center justify-between border border-border bg-raised px-2 py-1.5 text-xs">
            <span>{instrumentLabel(instrument)} · lot {instrument.lot_size}</span>
            <Button type="button" size="xs" variant="ghost" onClick={() => setInstrument(null)}>change</Button>
          </div>
        ) : (
          <InstrumentSearch onPick={setInstrument} placeholder="Search NIFTY, BANKNIFTY, RELIANCE…" />
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-start">Start (IST day)</Label>
          <Input id="bt-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} className="h-8 text-xs" required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-end">End</Label>
          <Input id="bt-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="h-8 text-xs" required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-tf">Timeframe</Label>
          <select id="bt-tf" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe | "")} className={SEL}>
            <option value="">{dslTf ? `from DSL (${dslTf})` : "from DSL"}</option>
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-cap">Capital (₹)</Label>
          <Input id="bt-cap" type="number" min={1000} step={1000} value={capital} onChange={(e) => setCapital(e.target.value)} className="h-8 text-xs tabular" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-slip">Slippage model</Label>
          <select id="bt-slip" value={slipModel} onChange={(e) => setSlipModel(e.target.value as SlippageModel)} className={SEL}>
            <option value="spread_aware">spread aware</option>
            <option value="fixed_bps">fixed bps</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-bps">Slippage (bps)</Label>
          <Input id="bt-bps" type="number" min={0} step={0.5} value={bps} onChange={(e) => setBps(e.target.value)} className="h-8 text-xs tabular" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-fill">Fill mode</Label>
          <select id="bt-fill" value={fillMode} onChange={(e) => setFillMode(e.target.value as FillMode)} className={SEL}>
            <option value="next_bar_open">next bar open (realistic)</option>
            <option value="bar_close">bar close (optimistic)</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bt-seed">Seed</Label>
          <Input id="bt-seed" type="number" value={seed} onChange={(e) => setSeed(e.target.value)} className="h-8 text-xs tabular" />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="bt-label">Label (optional)</Label>
        <Input id="bt-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. EMA 9/21 · 1y · spread-aware" className="h-8 text-xs" />
      </div>
      {err && <p className="text-[11px] text-down">{err}</p>}
      <Button type="submit" disabled={!chosenVersionId || !instrument || create.isPending}>
        <Play /> Run backtest
      </Button>
      <p className="text-[11px] text-text-3">Runs in the worker on stored 1-minute candles. Same engine, risk rules and simulator as paper trading.</p>
    </form>
  );
}
