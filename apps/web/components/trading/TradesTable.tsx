"use client";

import { Dash, EmptyState, Money } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { PaperTrade } from "@/lib/api/generated";
import { formatDateTime, formatNumber } from "@/lib/format";
import { num } from "@/lib/ws/useMarket";
import { SideText } from "./StatusChip";

export function TradesTable({ trades, isPending, showAccount }: { trades: PaperTrade[] | undefined; isPending?: boolean; showAccount?: (t: PaperTrade) => string }) {
  if (isPending) return <Skeleton className="m-3 h-20" />;
  if (!trades || trades.length === 0) return <EmptyState title="No closed trades yet" description="A trade is recorded when a position returns to flat." className="m-3" />;
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-muted">
        <tr className="border-b border-border-subtle">
          {showAccount && <th className="px-3 py-1.5 text-left font-medium">Account</th>}
          <th className="px-3 py-1.5 text-left font-medium">Symbol</th>
          <th className="px-3 py-1.5 text-left font-medium">Side</th>
          <th className="px-3 py-1.5 text-right font-medium">Qty</th>
          <th className="px-3 py-1.5 text-left font-medium">Entry</th>
          <th className="px-3 py-1.5 text-right font-medium">Entry px</th>
          <th className="px-3 py-1.5 text-left font-medium">Exit</th>
          <th className="px-3 py-1.5 text-right font-medium">Exit px</th>
          <th className="px-3 py-1.5 text-right font-medium">Gross</th>
          <th className="px-3 py-1.5 text-right font-medium">Costs</th>
          <th className="px-3 py-1.5 text-right font-medium">Net</th>
          <th className="px-3 py-1.5 text-right font-medium">Bars</th>
          <th className="px-3 py-1.5 text-left font-medium">Reasons</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((t) => (
          <tr key={t.id} className="border-b border-border-subtle/60">
            {showAccount && <td className="px-3 py-1.5 text-text-secondary">{showAccount(t)}</td>}
            <td className="px-3 py-1.5 text-text-primary">{t.symbol ?? `#${t.instrument_id}`}</td>
            <td className="px-3 py-1.5"><SideText side={t.side} /></td>
            <td className="px-3 py-1.5 text-right tabular">{formatNumber(t.quantity)}</td>
            <td className="px-3 py-1.5 tabular text-text-secondary">{formatDateTime(t.entry_at)}</td>
            <td className="px-3 py-1.5 text-right tabular">{formatNumber(Number(t.entry_price), 2)}</td>
            <td className="px-3 py-1.5 tabular text-text-secondary">{formatDateTime(t.exit_at)}</td>
            <td className="px-3 py-1.5 text-right tabular">{formatNumber(Number(t.exit_price), 2)}</td>
            <td className="px-3 py-1.5 text-right"><Money value={num(t.gross_pnl)} signed muted /></td>
            <td className="px-3 py-1.5 text-right"><Money value={num(t.costs)} muted /></td>
            <td className="px-3 py-1.5 text-right"><Money value={num(t.net_pnl)} signed /></td>
            <td className="px-3 py-1.5 text-right tabular text-text-secondary">{t.bars_held ?? <Dash />}</td>
            <td className="max-w-72 truncate px-3 py-1.5 text-text-secondary" title={`${t.entry_reason ?? ""} → ${t.exit_reason ?? ""}`}>
              {t.entry_reason ?? "—"} → {t.exit_reason ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
