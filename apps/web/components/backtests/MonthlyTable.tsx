"use client";

import { EmptyState } from "@/components/design";
import { metricNumber } from "@/lib/backtest-utils";
import { cn } from "@/lib/utils";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Accepts either a list of {year, month, pnl|return_pct} rows or a {year: {month: value}} map. */
export function MonthlyTable({ table }: { table: unknown }) {
  const grid = new Map<number, Map<number, number>>();
  let isPct = false;
  const put = (y: number, m: number, v: number) => {
    if (!grid.has(y)) grid.set(y, new Map());
    grid.get(y)!.set(m, v);
  };
  if (Array.isArray(table)) {
    for (const r of table as Record<string, unknown>[]) {
      if (!r || typeof r !== "object") continue;
      let y = metricNumber(r.year);
      let m = metricNumber(r.month);
      if ((y == null || m == null) && typeof r.month === "string" && /^\d{4}-\d{2}/.test(r.month)) {
        y = Number(r.month.slice(0, 4));
        m = Number(r.month.slice(5, 7));
      }
      const pct = metricNumber(r.return_pct ?? r.pct);
      const v = pct ?? metricNumber(r.pnl ?? r.net_pnl ?? r.value);
      if (pct != null) isPct = true;
      if (y != null && m != null && v != null) put(y, m, v);
    }
  } else if (table && typeof table === "object") {
    for (const [yk, months] of Object.entries(table as Record<string, unknown>)) {
      const y = Number(yk);
      if (!Number.isFinite(y) || !months || typeof months !== "object") continue;
      for (const [mk, v] of Object.entries(months as Record<string, unknown>)) {
        const m = Number(mk);
        const n = metricNumber(v);
        if (Number.isFinite(m) && n != null) put(y, m, n);
      }
    }
  }
  const years = Array.from(grid.keys()).sort();
  if (years.length === 0) return <EmptyState title="No monthly data" description="The result did not include a monthly table." />;
  const all = years.flatMap((y) => Array.from(grid.get(y)!.values()));
  const max = Math.max(1e-9, ...all.map((v) => Math.abs(v)));
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-muted">
        <tr className="border-b border-border-subtle">
          <th className="px-2 py-1 text-left font-medium">Year</th>
          {MONTHS.map((m) => <th key={m} className="px-1 py-1 text-right font-medium">{m}</th>)}
          <th className="px-2 py-1 text-right font-medium">Total</th>
        </tr>
      </thead>
      <tbody>
        {years.map((y) => {
          const row = grid.get(y)!;
          const total = Array.from(row.values()).reduce((a, b) => a + b, 0);
          return (
            <tr key={y} className="border-b border-border-subtle/60">
              <td className="px-2 py-1 tabular text-text-secondary">{y}</td>
              {MONTHS.map((_, i) => {
                const v = row.get(i + 1);
                const a = v == null ? 0 : Math.min(1, Math.abs(v) / max);
                return (
                  <td
                    key={i}
                    className={cn("px-1 py-1 text-right tabular", v == null ? "text-text-muted" : v > 0 ? "text-pnl-positive" : v < 0 ? "text-pnl-negative" : "text-text-secondary")}
                    style={v == null ? undefined : { background: v > 0 ? `rgba(34,197,94,${0.08 + a * 0.3})` : v < 0 ? `rgba(239,68,68,${0.08 + a * 0.3})` : undefined }}
                  >
                    {v == null ? "—" : isPct ? `${v.toFixed(1)}%` : v.toFixed(0)}
                  </td>
                );
              })}
              <td className={cn("px-2 py-1 text-right font-semibold tabular", total > 0 ? "text-pnl-positive" : total < 0 ? "text-pnl-negative" : "")}>
                {isPct ? `${total.toFixed(1)}%` : total.toFixed(0)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
