"use client";

import { Play, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { isoDay } from "@/components/backtests/BacktestForm";
import { JobStatusChip, ProgressBar } from "@/components/backtests/JobStatus";
import { StrategyVersionPicker } from "@/components/backtests/StrategyVersionPicker";
import { EmptyState, PanelCard } from "@/components/design";
import { InstrumentSearch, instrumentLabel } from "@/components/market/InstrumentSearch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateOptimization, useOptimizations } from "@/lib/api/backtests";
import { ApiRequestError } from "@/lib/api/client";
import type { Instrument, Objective, OptimizationKind, StrategyVersion } from "@/lib/api/generated";
import { formatDateTime } from "@/lib/format";

const SEL = "h-8 border border-border bg-raised px-2 text-xs";
const HINTS = ["indicators.ema9.params.period", "indicators.ema21.params.period", "indicators.rsi14.params.period", "stop_loss.value", "target.value", "position_sizing.lots"];

interface Row {
  path: string;
  values: string;
}

function parseValues(raw: string): unknown[] {
  return raw
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => (Number.isFinite(Number(v)) && v !== "" ? Number(v) : v === "true" ? true : v === "false" ? false : v));
}

function gridSize(rows: Row[]): number {
  return rows.reduce((n, r) => n * Math.max(1, parseValues(r.values).length), 1);
}

export default function OptimizePage() {
  const router = useRouter();
  const create = useCreateOptimization();
  const { data: jobs, isPending } = useOptimizations();
  const [strategyId, setStrategyId] = useState<number | null>(null);
  const [version, setVersion] = useState<StrategyVersion | null>(null);
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const today = new Date();
  const [start, setStart] = useState(isoDay(new Date(today.getTime() - 365 * 86400_000)));
  const [end, setEnd] = useState(isoDay(today));
  const [kind, setKind] = useState<OptimizationKind>("grid");
  const [objective, setObjective] = useState<Objective>("sharpe");
  const [maxRuns, setMaxRuns] = useState("200");
  const [rows, setRows] = useState<Row[]>([{ path: "indicators.ema9.params.period", values: "5, 8, 9, 12" }]);
  const [train, setTrain] = useState("120");
  const [test, setTest] = useState("30");
  const [step, setStep] = useState("30");
  const err = create.error instanceof ApiRequestError ? create.error.message : create.error ? "Cannot reach the API." : null;
  const size = gridSize(rows);
  const paramSpace = Object.fromEntries(rows.filter((r) => r.path.trim()).map((r) => [r.path.trim(), parseValues(r.values)]));

  return (
    <div className="grid grid-cols-12 gap-3">
      <PanelCard title="Optimise / walk-forward" subtitle="Parameter sweeps on the same data, costs and seed; walk-forward re-picks per window" className="col-span-12 xl:col-span-5">
        <form
          className="flex flex-col gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!version || !instrument) return;
            const job = await create.mutateAsync({
              strategy_version_id: version.id,
              instrument_id: instrument.instrument_id,
              start,
              end,
              kind,
              param_space: paramSpace,
              objective,
              max_runs: Number(maxRuns) || 200,
              windows: kind === "walk_forward" ? { train_days: Number(train), test_days: Number(test), step_days: Number(step) } : null,
            });
            router.push(`/backtesting/optimize/${job.id}`);
          }}
        >
          <StrategyVersionPicker strategyId={strategyId} versionId={version?.id ?? null} onStrategy={setStrategyId} onVersion={setVersion} idPrefix="opt" />
          <div className="flex flex-col gap-1.5">
            <Label>Instrument</Label>
            {instrument ? (
              <div className="flex items-center justify-between border border-border bg-raised px-2 py-1.5 text-xs">
                <span>{instrumentLabel(instrument)}</span>
                <Button type="button" size="xs" variant="ghost" onClick={() => setInstrument(null)}>change</Button>
              </div>
            ) : (
              <InstrumentSearch onPick={setInstrument} />
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1.5"><Label htmlFor="o-start">Start</Label><Input id="o-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} className="h-8 text-xs" /></div>
            <div className="flex flex-col gap-1.5"><Label htmlFor="o-end">End</Label><Input id="o-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="h-8 text-xs" /></div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="o-kind">Kind</Label>
              <select id="o-kind" value={kind} onChange={(e) => setKind(e.target.value as OptimizationKind)} className={SEL}>
                <option value="grid">grid (all combinations)</option>
                <option value="random">random (sample max runs)</option>
                <option value="walk_forward">walk-forward</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="o-obj">Objective</Label>
              <select id="o-obj" value={objective} onChange={(e) => setObjective(e.target.value as Objective)} className={SEL}>
                <option value="sharpe">sharpe</option>
                <option value="net_pnl">net P&L</option>
                <option value="calmar">calmar</option>
                <option value="expectancy">expectancy</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5"><Label htmlFor="o-max">Max runs</Label><Input id="o-max" type="number" min={1} max={2000} value={maxRuns} onChange={(e) => setMaxRuns(e.target.value)} className="h-8 text-xs tabular" /></div>
          </div>
          {kind === "walk_forward" && (
            <div className="grid grid-cols-3 gap-2 rounded-sm border border-border p-2">
              <div className="flex flex-col gap-1.5"><Label htmlFor="o-train">Train days</Label><Input id="o-train" type="number" value={train} onChange={(e) => setTrain(e.target.value)} className="h-8 text-xs tabular" /></div>
              <div className="flex flex-col gap-1.5"><Label htmlFor="o-test">Test days</Label><Input id="o-test" type="number" value={test} onChange={(e) => setTest(e.target.value)} className="h-8 text-xs tabular" /></div>
              <div className="flex flex-col gap-1.5"><Label htmlFor="o-step">Step days</Label><Input id="o-step" type="number" value={step} onChange={(e) => setStep(e.target.value)} className="h-8 text-xs tabular" /></div>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Label>Parameter space</Label>
              <span className="text-[11px] text-text-3">{size.toLocaleString("en-IN")} combination(s)</span>
            </div>
            {rows.map((r, i) => (
              <div key={i} className="flex items-center gap-1">
                <Input list="param-hints" value={r.path} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, path: e.target.value } : x)))} placeholder="dotted.path" className="h-8 flex-1 font-mono text-[11px]" />
                <Input value={r.values} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, values: e.target.value } : x)))} placeholder="5, 8, 13" className="h-8 flex-1 font-mono text-[11px]" />
                <Button type="button" size="xs" variant="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label="Remove"><Trash2 /></Button>
              </div>
            ))}
            <datalist id="param-hints">{HINTS.map((h) => <option key={h} value={h} />)}</datalist>
            <Button type="button" size="xs" variant="ghost" onClick={() => setRows([...rows, { path: "", values: "" }])}><Plus /> add parameter</Button>
            <p className="text-[11px] text-text-3">Paths point into the DSL: indicators.&lt;id&gt;.params.&lt;name&gt;, stop_loss.value, target.value, position_sizing.lots.</p>
          </div>
          {err && <p className="text-[11px] text-down">{err}</p>}
          <Button type="submit" disabled={!version || !instrument || rows.length === 0 || create.isPending}><Play /> Run {kind.replace("_", "-")}</Button>
        </form>
      </PanelCard>

      <PanelCard title="Optimisation jobs" className="col-span-12 xl:col-span-7" bodyClassName="p-0">
        {isPending ? <Skeleton className="m-3 h-24" /> : !jobs || jobs.length === 0 ? (
          <EmptyState title="No optimisation jobs yet" className="m-3" />
        ) : (
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-text-3">
              <tr className="border-b border-border">
                <th className="px-2 py-1.5 text-left font-medium">Job</th>
                <th className="px-2 py-1.5 text-left font-medium">Kind</th>
                <th className="px-2 py-1.5 text-left font-medium">Objective</th>
                <th className="px-2 py-1.5 text-left font-medium">Params</th>
                <th className="px-2 py-1.5 text-left font-medium">Status</th>
                <th className="px-2 py-1.5 text-left font-medium">Queued</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-b border-border/60">
                  <td className="px-2 py-1.5"><Link href={`/backtesting/optimize/${j.id}`} className="text-text-1 hover:text-accent-cyan">#{j.id} · v#{j.strategy_version_id} · #{j.instrument_id}</Link></td>
                  <td className="px-2 py-1.5 text-text-2">{j.kind.replace("_", " ")}</td>
                  <td className="px-2 py-1.5 text-text-2">{j.objective}</td>
                  <td className="px-2 py-1.5 font-mono text-[10px] text-text-2">{Object.keys(j.param_space).join(", ")}</td>
                  <td className="px-2 py-1.5"><div className="flex flex-col gap-1"><JobStatusChip status={j.status} />{j.status === "running" && <ProgressBar pct={j.progress_pct} className="w-24" />}</div></td>
                  <td className="px-2 py-1.5 tabular text-text-2">{formatDateTime(j.queued_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>
    </div>
  );
}
