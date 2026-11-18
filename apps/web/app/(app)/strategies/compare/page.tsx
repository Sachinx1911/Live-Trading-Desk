"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { CurveChart, type CurveSeries } from "@/components/backtests/CurveChart";
import { METRIC_COLUMNS, MetricValue } from "@/components/backtests/MetricsGrid";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { backtestKeys } from "@/lib/api/backtests";
import type { BacktestResultOut } from "@/lib/api/generated";
import { normaliseCurve, useCompareList, writeCompareList } from "@/lib/backtest-utils";

export default function ComparePage() {
  const ids = useCompareList();
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: backtestKeys.results(id),
      queryFn: () => api<BacktestResultOut>(`/backtests/${id}/results`),
      retry: false,
    })),
  });
  const loaded = results.map((r, i) => ({ id: ids[i], data: r.data, error: r.isError })).filter((r) => r.data || r.error);

  const series: CurveSeries[] = useMemo(
    () =>
      loaded
        .filter((r) => r.data)
        .map((r) => {
          const pts = normaliseCurve(r.data!.equity_curve, ["equity", "value", "y"]);
          const base = pts[0]?.value || 1;
          return { id: String(r.id), label: `#${r.id}${r.data!.job.label ? ` ${r.data!.job.label}` : ""}`, points: pts.map((p) => ({ ts: p.ts, value: (p.value / base) * 100 })) };
        }),
    [loaded],
  );

  const remove = (id: number) => writeCompareList(ids.filter((x) => x !== id));

  return (
    <div className="flex flex-col gap-3">
      <PanelCard title="Strategy comparison" subtitle="Backtest jobs you added from their result pages. Equity is normalised to 100 at the first point." actions={<Link href="/backtesting" className="text-[11px] text-accent-cyan">backtests →</Link>}>
        {ids.length === 0 ? (
          <EmptyState title="Nothing to compare" description='Open a finished backtest and click "add to compare".' />
        ) : (
          <div className="flex flex-wrap gap-2">
            {ids.map((id) => (
              <span key={id} className="inline-flex items-center gap-1 rounded-sm border border-border-subtle bg-panel-raised px-2 py-1 text-xs">
                <Link href={`/backtesting/${id}`} className="hover:text-accent-cyan">#{id}</Link>
                <Button size="xs" variant="ghost" onClick={() => remove(id)} aria-label="Remove"><X /></Button>
              </span>
            ))}
          </div>
        )}
      </PanelCard>
      {ids.length > 0 && (
        <>
          <PanelCard title="Normalised equity" bodyClassName="p-0">
            <CurveChart series={series} height={300} emptyTitle="No equity curves loaded yet" />
          </PanelCard>
          <PanelCard title="Metrics side by side" bodyClassName="p-0 overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase tracking-wide text-text-muted">
                <tr className="border-b border-border-subtle">
                  <th className="px-2 py-1.5 text-left font-medium">Metric</th>
                  {loaded.map((r) => <th key={r.id} className="px-2 py-1.5 text-right font-medium">#{r.id}{r.data?.job.label ? ` · ${r.data.job.label}` : ""}</th>)}
                </tr>
              </thead>
              <tbody>
                {METRIC_COLUMNS.map((m) => (
                  <tr key={m.key} className="border-b border-border-subtle/60">
                    <td className="px-2 py-1.5 text-text-secondary">{m.label}</td>
                    {loaded.map((r) => <td key={r.id} className="px-2 py-1.5 text-right">{r.data ? <MetricValue kind={m.kind} value={r.data.metrics[m.key]} signed={m.signed} /> : <span className="text-pnl-negative">no result</span>}</td>)}
                  </tr>
                ))}
                <tr><td className="px-2 py-1.5 text-text-secondary">Config hash</td>{loaded.map((r) => <td key={r.id} className="px-2 py-1.5 text-right font-mono text-[10px] text-text-muted">{r.data?.job.config_hash.slice(0, 10) ?? "—"}</td>)}</tr>
                <tr><td className="px-2 py-1.5 text-text-secondary">Data hash</td>{loaded.map((r) => <td key={r.id} className="px-2 py-1.5 text-right font-mono text-[10px] text-text-muted">{r.data?.data_hash?.slice(0, 10) ?? "—"}</td>)}</tr>
              </tbody>
            </table>
          </PanelCard>
        </>
      )}
    </div>
  );
}
