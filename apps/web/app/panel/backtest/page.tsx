"use client";

import { Suspense, useMemo } from "react";
import { CurveChart } from "@/components/backtests/CurveChart";
import { ProgressBar } from "@/components/backtests/JobStatus";
import { MetricsGrid } from "@/components/backtests/MetricsGrid";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { ApiRequestError } from "@/lib/api/client";
import { useBacktest, useBacktestResults } from "@/lib/api/backtests";
import { normaliseCurve } from "@/lib/backtest-utils";
import { formatDateTime } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";
import { cn } from "@/lib/utils";

const BANNER: Record<string, string> = {
  succeeded: "border-accent/60 text-text-1",
  partial: "border-warn/60 text-warn",
  failed: "border-down/70 text-down",
  cancelled: "border-border text-text-3",
  queued: "border-border text-text-2",
  running: "border-accent/60 text-accent-text",
};

/** One backtest: full-width status banner, key metrics, equity and drawdown. Read-only. */
function BacktestPanel() {
  const { values, errors } = usePanelParams("backtest");
  const id = errors.length || values.job == null ? null : Number(values.job);
  const job = useBacktest(id);
  const done = job.data?.status === "succeeded" || job.data?.status === "partial" || !!job.data?.has_result;
  const res = useBacktestResults(id, done);
  const equity = useMemo(() => normaliseCurve(res.data?.equity_curve, ["equity", "value", "y"]), [res.data]);
  const drawdown = useMemo(() => normaliseCurve(res.data?.drawdown_curve, ["drawdown", "dd", "value", "y"]), [res.data]);
  const eqSeries = useMemo(() => [{ id: "equity", label: "Equity", points: equity, area: true }], [equity]);
  const ddSeries = useMemo(() => [{ id: "dd", label: "Drawdown", points: drawdown, area: true, color: "#f23645" }], [drawdown]);

  const j = job.data;
  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="backtest"
      subtitle={j ? `#${j.id}${j.label ? ` · ${j.label}` : ""} · ${j.timeframe}` : values.job ? `#${values.job}` : undefined}
      state={j ? "historical" : job.isError && !(job.error instanceof ApiRequestError && job.error.status === 404) ? "disconnected" : undefined}
      stateDetail={j ? "stored result" : undefined}
      fullHref={j ? fullPageUrl("backtest", { job: String(j.id) }) : "/backtesting"}
      bodyClassName="flex flex-col"
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="backtest" errors={errors} />);
  if (job.isPending) return frame(<PanelMessage title="Loading backtest…" />);
  if (job.error instanceof ApiRequestError && job.error.status === 404) return frame(<PanelMessage tone="error" title={`job: backtest #${id} not found`} />);
  if (job.isError || !j) return frame(<PanelMessage tone="error" title="Cannot reach the API" />);

  return frame(
    <>
      <div className={cn("hud-glow mx-2 mt-2 flex shrink-0 flex-wrap items-baseline gap-x-4 gap-y-1 rounded-[var(--r-sm)] border bg-pane px-3 py-2", BANNER[j.status] ?? "border-border")}>
        <span className="font-mono text-[clamp(16px,2.4vw,28px)] font-semibold tracking-wider uppercase">
          Backtest #{j.id} · {j.status}
        </span>
        <span className="truncate text-[12px] text-text-3">
          version #{j.strategy_version_id} · instrument #{j.instrument_id} · {formatDateTime(j.start_at)} → {formatDateTime(j.end_at)} · seed {j.seed}
        </span>
        {j.status === "running" && <ProgressBar pct={j.progress_pct} className="w-full max-w-md" />}
        {j.error && <span className="w-full text-[12px] text-down">{j.error}</span>}
      </div>
      {!done ? (
        <PanelMessage title={j.status === "queued" ? "Queued in the worker" : j.status === "running" ? `Running · ${j.progress_pct.toFixed(0)}%` : "No result stored"} />
      ) : res.isPending ? (
        <PanelMessage title="Loading results…" />
      ) : res.isError || !res.data ? (
        <PanelMessage tone="error" title="Results not available" description="The job finished but no result row was found." />
      ) : (
        <>
          <div className="shrink-0 p-2">
            <MetricsGrid metrics={res.data.metrics} />
          </div>
          {res.data.warnings?.length ? <p className="shrink-0 px-3 text-[11px] text-warn">{res.data.warnings.join(" · ")}</p> : null}
          <div className="flex min-h-[200px] flex-1 flex-col gap-px px-2 pb-2">
            <div className="min-h-0 flex-[3]">
              <CurveChart series={eqSeries} height="fill" emptyTitle="No equity curve" />
            </div>
            <div className="min-h-0 flex-1 border-t border-border">
              <CurveChart series={ddSeries} height="fill" emptyTitle="No drawdown curve" />
            </div>
          </div>
        </>
      )}
    </>,
  );
}

export default function BacktestPanelPage() {
  return (
    <Suspense>
      <BacktestPanel />
    </Suspense>
  );
}
