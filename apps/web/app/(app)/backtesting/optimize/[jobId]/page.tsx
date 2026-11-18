"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CurveChart } from "@/components/backtests/CurveChart";
import { JobStatusChip, ProgressBar } from "@/components/backtests/JobStatus";
import { METRIC_COLUMNS, MetricValue } from "@/components/backtests/MetricsGrid";
import { EmptyState, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import { useOptimization, useOptimizationResults } from "@/lib/api/backtests";
import type { CurvePoint } from "@/lib/api/generated";
import { normaliseCurve } from "@/lib/backtest-utils";
import { cn } from "@/lib/utils";

const SHOW = ["sharpe", "net_pnl", "total_return", "max_drawdown_pct", "win_rate", "profit_factor", "expectancy", "total_trades", "calmar"];

function flags(obj: unknown): string[] {
  if (!obj || typeof obj !== "object") return [];
  const f = (obj as Record<string, unknown>).flags ?? (obj as Record<string, unknown>).overfitting_flags;
  if (Array.isArray(f)) return f.map(String);
  if (f && typeof f === "object") return Object.entries(f as Record<string, unknown>).filter(([, v]) => v).map(([k, v]) => (typeof v === "string" ? v : k));
  return [];
}

export default function OptimizationDetailPage() {
  const params = useParams<{ jobId: string }>();
  const id = Number(params.jobId);
  const { data: job, isPending } = useOptimization(Number.isFinite(id) ? id : null);
  const done = job?.status === "succeeded" || job?.status === "partial";
  const { data: rows, isPending: rowsPending } = useOptimizationResults(id, !!done);
  const [expanded, setExpanded] = useState(true);

  const paramKeys = useMemo(() => Array.from(new Set((rows ?? []).flatMap((r) => Object.keys(r.params)))), [rows]);
  const metricCols = METRIC_COLUMNS.filter((m) => SHOW.includes(m.key) || (job?.objective && m.key === job.objective));
  const wf = job?.kind === "walk_forward";
  const oosRows = (rows ?? []).filter((r) => r.is_oos);
  const oosEquity = useMemo(() => normaliseCurve((job?.config?.oos_equity as CurvePoint[] | undefined) ?? null, ["equity", "value", "y"]), [job]);
  const allFlags = [...flags(job?.config), ...flags(job?.config?.results)];

  if (isPending) return <Skeleton className="h-64" />;
  if (!job) return <EmptyState title="Optimisation not found" />;

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title={`${job.kind.replace("_", " ")} #${job.id}`}
        subtitle={`version #${job.strategy_version_id} · instrument #${job.instrument_id} · objective ${job.objective}${job.windows ? ` · windows ${JSON.stringify(job.windows)}` : ""}`}
        actions={
          <div className="flex items-center gap-2">
            <JobStatusChip status={job.status} />
            {job.best_backtest_job_id && <Link href={`/backtesting/${job.best_backtest_job_id}`} className="text-[11px] text-accent-cyan">best backtest →</Link>}
          </div>
        }
      >
        {job.status === "running" && <ProgressBar pct={job.progress_pct} className="max-w-md" />}
        {job.error && <p className="text-xs text-pnl-negative">{job.error}</p>}
        <p className="mt-1 font-mono text-[11px] text-text-muted">{Object.entries(job.param_space).map(([k, v]) => `${k} ∈ {${v.join(", ")}}`).join("  ·  ")}</p>
        {allFlags.length > 0 && (
          <div role="alert" className="mt-2 rounded-sm border border-state-delayed/40 bg-state-delayed/10 px-3 py-2 text-xs text-state-delayed">
            Overfitting flags: {allFlags.join("; ")}
          </div>
        )}
      </PanelCard>

      {wf && done && (
        <PanelCard title="Out-of-sample equity (stitched)" bodyClassName="p-0">
          <CurveChart series={[{ id: "oos", label: "OOS equity", points: oosEquity, area: true }]} height={220} emptyTitle="No stitched OOS curve in the result" />
        </PanelCard>
      )}

      <PanelCard
        title={wf ? "Windows (in-sample pick vs out-of-sample result)" : "Ranked results"}
        subtitle={rows ? `${rows.length} row(s)${wf ? ` · ${oosRows.length} OOS` : ""}` : undefined}
        bodyClassName="p-0 overflow-x-auto"
        actions={<button type="button" className="text-[11px] text-accent-cyan" onClick={() => setExpanded(!expanded)}>{expanded ? "collapse params" : "expand params"}</button>}
      >
        {!done ? (
          <EmptyState title="Waiting for the job to finish" className="m-3" />
        ) : rowsPending ? (
          <Skeleton className="m-3 h-24" />
        ) : !rows || rows.length === 0 ? (
          <EmptyState title="No results rows" className="m-3" />
        ) : (
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-text-muted">
              <tr className="border-b border-border-subtle">
                <th className="px-2 py-1.5 text-right font-medium">#</th>
                {wf && <th className="px-2 py-1.5 text-left font-medium">Window</th>}
                {wf && <th className="px-2 py-1.5 text-left font-medium">Set</th>}
                {expanded ? paramKeys.map((k) => <th key={k} className="px-2 py-1.5 text-right font-mono font-medium normal-case">{k.split(".").slice(-2).join(".")}</th>) : <th className="px-2 py-1.5 text-left font-medium">Params</th>}
                {metricCols.map((m) => <th key={m.key} className={cn("px-2 py-1.5 text-right font-medium", m.key === job.objective && "text-accent-cyan")}>{m.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={cn("border-b border-border-subtle/60", r.rank === 1 && !wf && "bg-accent-cyan/5")}>
                  <td className="px-2 py-1.5 text-right tabular text-text-secondary">{r.rank}</td>
                  {wf && <td className="px-2 py-1.5 font-mono text-[10px] text-text-secondary">{r.window ? `${String(r.window.train_start ?? r.window.start ?? "").slice(0, 10)} → ${String(r.window.test_end ?? r.window.end ?? "").slice(0, 10)}` : "—"}</td>}
                  {wf && <td className="px-2 py-1.5"><span className={cn("rounded-sm border px-1 text-[10px] uppercase", r.is_oos ? "border-accent-cyan/40 text-accent-cyan" : "border-border-subtle text-text-muted")}>{r.is_oos ? "OOS" : "IS"}</span></td>}
                  {expanded ? paramKeys.map((k) => <td key={k} className="px-2 py-1.5 text-right font-mono tabular">{r.params[k] == null ? "—" : String(r.params[k])}</td>) : <td className="px-2 py-1.5 font-mono text-[10px]">{Object.entries(r.params).map(([k, v]) => `${k.split(".").slice(-1)[0]}=${String(v)}`).join(" ")}</td>}
                  {metricCols.map((m) => <td key={m.key} className="px-2 py-1.5 text-right"><MetricValue kind={m.kind} value={r.metrics[m.key]} signed={m.signed} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>
    </div>
  );
}
