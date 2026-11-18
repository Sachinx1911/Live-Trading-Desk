"use client";

import { Dash, Money, Pct } from "@/components/design";
import type { BacktestMetrics } from "@/lib/api/generated";
import { metricNumber } from "@/lib/backtest-utils";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Kind = "pct" | "money" | "ratio" | "count" | "num";

const SPEC: { key: keyof BacktestMetrics & string; label: string; kind: Kind; signed?: boolean }[] = [
  { key: "total_return_pct", label: "Total return", kind: "pct", signed: true },
  { key: "total_return", label: "Net P&L (₹)", kind: "money", signed: true },
  { key: "cagr_pct", label: "CAGR", kind: "pct", signed: true },
  { key: "max_drawdown_pct", label: "Max drawdown", kind: "pct" },
  { key: "max_drawdown", label: "Max DD (₹)", kind: "money" },
  { key: "sharpe", label: "Sharpe", kind: "ratio" },
  { key: "sortino", label: "Sortino", kind: "ratio" },
  { key: "calmar", label: "Calmar", kind: "ratio" },
  { key: "profit_factor", label: "Profit factor", kind: "ratio" },
  { key: "win_rate_pct", label: "Win rate", kind: "pct" },
  { key: "expectancy", label: "Expectancy / trade", kind: "money", signed: true },
  { key: "avg_win", label: "Avg win", kind: "money", signed: true },
  { key: "avg_loss", label: "Avg loss", kind: "money", signed: true },
  { key: "payoff_ratio", label: "Payoff ratio", kind: "ratio" },
  { key: "total_trades", label: "Trades", kind: "count" },
  { key: "wins", label: "Wins", kind: "count" },
  { key: "losses", label: "Losses", kind: "count" },
  { key: "max_consecutive_losses", label: "Max consecutive losses", kind: "count" },
  { key: "exposure_time_pct", label: "Exposure time", kind: "pct" },
  { key: "avg_bars_held", label: "Avg bars held", kind: "num" },
  { key: "avg_mae", label: "Avg MAE", kind: "money" },
  { key: "avg_mfe", label: "Avg MFE", kind: "money" },
  { key: "fees_total", label: "Fees total", kind: "money" },
  { key: "turnover", label: "Turnover", kind: "money" },
  { key: "max_dd_duration_days", label: "DD duration (days)", kind: "num" },
];

export function MetricValue({ kind, value, signed }: { kind: Kind; value: unknown; signed?: boolean }) {
  if (kind === "num" && typeof value === "string" && value && Number.isNaN(Number(value))) return <span className="tabular">{value}</span>;
  const n = metricNumber(value);
  if (n == null) return <Dash />;
  if (kind === "pct") return <Pct value={n} signed={!!signed} />;
  if (kind === "money") return <Money value={n} signed={!!signed} muted={!signed} />;
  if (kind === "count") return <span className="tabular">{formatNumber(n)}</span>;
  return <span className={cn("tabular", signed && (n > 0 ? "text-pnl-positive" : n < 0 ? "text-pnl-negative" : ""))}>{formatNumber(n, 2)}</span>;
}

export function MetricsGrid({ metrics, compact = false }: { metrics: BacktestMetrics; compact?: boolean }) {
  return (
    <div className={cn("grid gap-2", compact ? "grid-cols-2 md:grid-cols-4" : "grid-cols-2 md:grid-cols-4 xl:grid-cols-6")}>
      {SPEC.map((m) => (
        <div key={m.key} className="rounded-sm border border-border-subtle bg-panel-raised px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-text-muted">{m.label}</p>
          <p className="mt-0.5 text-base font-semibold text-text-primary">
            <MetricValue kind={m.kind} value={metrics[m.key]} signed={m.signed} />
          </p>
        </div>
      ))}
    </div>
  );
}

export const METRIC_COLUMNS = SPEC;
