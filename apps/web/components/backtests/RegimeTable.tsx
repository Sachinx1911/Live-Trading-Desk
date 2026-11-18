"use client";

import { Money } from "@/components/design";
import type { RegimeTableRow } from "@/lib/api/generated";
import { formatNumber, formatPct } from "@/lib/format";
import { num } from "@/lib/ws/useMarket";

const GROUPS: { key: RegimeTableRow["group"]; title: string }[] = [
  { key: "trend_vol", title: "Trend × volatility (daily)" },
  { key: "day_type", title: "Day type (intraday)" },
];

/** Per-regime breakdown of a backtest: the fastest way to see where a strategy actually loses. */
export function RegimeTable({ rows }: { rows: RegimeTableRow[] | null | undefined }) {
  if (!rows) {
    return <p className="p-3 text-[12px] text-text-3">Regime breakdown is not available for this result yet; it is added when the regime job has classified the tested days.</p>;
  }
  if (rows.length === 0) return <p className="p-3 text-[12px] text-text-3">No trades to group.</p>;
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-3">
        <tr className="border-b border-border">
          <th className="px-3 py-1.5 text-left font-medium">Regime</th>
          <th className="px-3 py-1.5 text-right font-medium">Trades</th>
          <th className="px-3 py-1.5 text-right font-medium">Win %</th>
          <th className="px-3 py-1.5 text-right font-medium">Net P&L</th>
          <th className="px-3 py-1.5 text-right font-medium">Avg / trade</th>
        </tr>
      </thead>
      <tbody>
        {GROUPS.map((g) => {
          const group = rows.filter((r) => r.group === g.key);
          if (group.length === 0) return null;
          return [
            <tr key={`${g.key}-h`} className="border-b border-border/60 bg-app/40">
              <td colSpan={5} className="px-3 py-1 text-[10px] uppercase tracking-wide text-text-3">{g.title}</td>
            </tr>,
            ...group.map((r) => (
              <tr key={`${g.key}-${r.label}`} className="border-b border-border/60">
                <td className="px-3 py-1.5 text-text-1">{r.label}</td>
                <td className="px-3 py-1.5 text-right tabular">{formatNumber(r.trades)}</td>
                <td className="px-3 py-1.5 text-right tabular">{r.trades > 0 ? formatPct((r.wins / r.trades) * 100, 1, false) : "—"}</td>
                <td className="px-3 py-1.5 text-right"><Money value={num(r.net_pnl)} signed /></td>
                <td className="px-3 py-1.5 text-right"><Money value={num(r.avg_pnl)} signed muted /></td>
              </tr>
            )),
          ];
        })}
      </tbody>
    </table>
  );
}
