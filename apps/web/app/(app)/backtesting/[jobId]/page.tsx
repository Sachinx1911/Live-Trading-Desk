"use client";

import { Ban, GitCompare, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CurveChart } from "@/components/backtests/CurveChart";
import { JobStatusChip, ProgressBar } from "@/components/backtests/JobStatus";
import { Markdown } from "@/components/backtests/Markdown";
import { MetricsGrid } from "@/components/backtests/MetricsGrid";
import { MonthlyTable } from "@/components/backtests/MonthlyTable";
import { RegimeTable } from "@/components/backtests/RegimeTable";
import { BacktestTradesTable } from "@/components/backtests/BacktestTradesTable";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isLive, useBacktest, useBacktestReport, useBacktestResults, useBacktestTrades, useCancelBacktest } from "@/lib/api/backtests";
import { normaliseCurve, useCompareList, writeCompareList } from "@/lib/backtest-utils";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "overview" | "trades" | "report" | "assumptions";
const PAGE = 100;

export default function BacktestDetailPage() {
  const params = useParams<{ jobId: string }>();
  const id = Number(params.jobId);
  const { data: job, isPending } = useBacktest(Number.isFinite(id) ? id : null);
  const done = job?.status === "succeeded" || job?.status === "partial" || job?.has_result;
  const { data: res, isError: resErr } = useBacktestResults(id, !!done);
  const [tab, setTab] = useState<Tab>("overview");
  const [page, setPage] = useState(0);
  const { data: trades, isPending: tradesPending } = useBacktestTrades(id, page * PAGE, PAGE, !!done && tab === "trades");
  const { data: report } = useBacktestReport(id, !!done && tab === "report");
  const cancel = useCancelBacktest();
  const compareList = useCompareList();
  const inCompare = compareList.includes(id);

  const equity = useMemo(() => normaliseCurve(res?.equity_curve, ["equity", "value", "y"]), [res]);
  const drawdown = useMemo(() => normaliseCurve(res?.drawdown_curve, ["drawdown", "dd", "value", "y"]), [res]);
  const eqSeries = useMemo(() => [{ id: "equity", label: "Equity", points: equity, area: true }], [equity]);
  const ddSeries = useMemo(() => [{ id: "dd", label: "Drawdown", points: drawdown, area: true, color: "#f23645" }], [drawdown]);

  if (isPending) return <Skeleton className="h-64" />;
  if (!job) return <EmptyState title="Backtest not found" />;

  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "trades", label: "Trades" },
    { key: "report", label: "Report" },
    { key: "assumptions", label: "Assumptions" },
  ];

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title={`Backtest #${job.id}${job.label ? ` · ${job.label}` : ""}`}
        subtitle={`version #${job.strategy_version_id} · instrument #${job.instrument_id} · ${job.timeframe} · ${formatDateTime(job.start_at)} → ${formatDateTime(job.end_at)} · seed ${job.seed}`}
        actions={
          <div className="flex items-center gap-2">
            <JobStatusChip status={job.status} />
            {isLive(job.status) && <Button size="xs" variant="ghost" onClick={() => cancel.mutate(job.id)}><Ban /> cancel</Button>}
            {done && (
              <Button
                size="xs"
                variant={inCompare ? "secondary" : "outline"}
                onClick={() => writeCompareList(inCompare ? compareList.filter((x) => x !== job.id) : [...compareList, job.id])}
              >
                <GitCompare /> {inCompare ? "in compare list" : "add to compare"}
              </Button>
            )}
            <Link href="/strategies/compare" className="text-[11px] text-accent-cyan">compare →</Link>
          </div>
        }
      >
        {job.status === "running" && (
          <div className="flex items-center gap-3 text-xs text-text-2">
            <RefreshCw className="size-3 animate-spin" /> running · {job.progress_pct.toFixed(0)}%
            <ProgressBar pct={job.progress_pct} className="max-w-md" />
          </div>
        )}
        {job.status === "queued" && <p className="text-xs text-text-2">Queued. The worker picks it up next; make sure <code>make worker</code> is running.</p>}
        {job.error && <p className="text-xs text-down">{job.error}</p>}
        {res?.warnings?.length ? (
          <ul className="mt-2 list-disc pl-5 text-[11px] text-warn">{res.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        ) : null}
        {res?.elapsed_s != null && <p className="mt-1 text-[11px] text-text-3">computed in {res.elapsed_s.toFixed(1)} s · config {job.config_hash.slice(0, 12)} · data {res.data_hash?.slice(0, 12) ?? "—"}</p>}
      </PanelCard>

      {!done ? null : resErr || !res ? (
        <EmptyState title="Results not available yet" description="The job finished but no result row was found." />
      ) : (
        <>
          <div className="flex gap-1 border-b border-border">
            {tabs.map((t) => (
              <button key={t.key} type="button" onClick={() => setTab(t.key)} className={cn("px-3 py-1.5 text-xs", tab === t.key ? "border-b-2 border-accent-cyan text-accent-cyan" : "text-text-3 hover:text-text-2")}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <div className="flex flex-col gap-3">
              <MetricsGrid metrics={res.metrics} />
              <PanelCard title="By regime" subtitle="Trades grouped by the deterministic regime of their entry day" bodyClassName="p-0 overflow-x-auto">
                <RegimeTable rows={res.regime_table} />
              </PanelCard>
              <div className="grid grid-cols-12 gap-3">
                <PanelCard title="Equity curve" className="col-span-12 xl:col-span-8" bodyClassName="p-0">
                  <CurveChart series={eqSeries} height={280} emptyTitle="No equity curve" />
                  <div className="border-t border-border">
                    <CurveChart series={ddSeries} height={140} emptyTitle="No drawdown curve" />
                  </div>
                </PanelCard>
                <PanelCard title="Monthly" className="col-span-12 xl:col-span-4" bodyClassName="p-0 overflow-x-auto">
                  <MonthlyTable table={res.monthly_table} />
                </PanelCard>
              </div>
            </div>
          )}

          {tab === "trades" && (
            <PanelCard title="Trades" subtitle={`page ${page + 1} · ${PAGE} per page`} bodyClassName="p-0 overflow-x-auto" actions={
              <div className="flex gap-1">
                <Button size="xs" variant="ghost" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>prev</Button>
                <Button size="xs" variant="ghost" disabled={!trades || trades.length < PAGE} onClick={() => setPage((p) => p + 1)}>next</Button>
              </div>
            }>
              <BacktestTradesTable trades={trades} isPending={tradesPending} />
            </PanelCard>
          )}

          {tab === "report" && (
            <PanelCard title="Deterministic report" subtitle="Generated from the result; no LLM involved">
              {report?.markdown ? <Markdown text={report.markdown} /> : <EmptyState title="No report" />}
            </PanelCard>
          )}

          {tab === "assumptions" && (
            <PanelCard title="Assumptions frozen with this result">
              <pre className="overflow-x-auto font-mono text-[11px] leading-snug text-text-1">{JSON.stringify({ assumptions: res.assumptions, engine_stats: res.engine_stats, config: job.config }, null, 2)}</pre>
            </PanelCard>
          )}
        </>
      )}
    </div>
  );
}
