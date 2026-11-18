"use client";

import { Dash, EmptyState, Money } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { PaperPosition } from "@/lib/api/generated";
import { formatDateTime, formatNumber } from "@/lib/format";
import { num, useLiveQuote } from "@/lib/ws/useMarket";

function Row({ p }: { p: PaperPosition }) {
  const { quote } = useLiveQuote(p.closed_at ? null : p.instrument_id);
  const live = num(quote?.ltp);
  const last = live ?? num(p.last_price);
  const avg = num(p.avg_price);
  const unreal = p.closed_at ? null : last != null && avg != null ? (last - avg) * p.quantity : num(p.unrealized_pnl);
  return (
    <tr className="border-b border-border/60">
      <td className="px-3 py-1.5 text-text-1">{p.symbol ?? `#${p.instrument_id}`}</td>
      <td className="px-3 py-1.5 uppercase text-text-2">{p.product}</td>
      <td className={`px-3 py-1.5 text-right tabular font-semibold ${p.quantity > 0 ? "text-up" : p.quantity < 0 ? "text-down" : "text-text-3"}`}>
        {p.quantity > 0 ? "+" : ""}{formatNumber(p.quantity)}
      </td>
      <td className="px-3 py-1.5 text-right tabular text-text-1">{avg != null ? formatNumber(avg, 2) : <Dash />}</td>
      <td className="px-3 py-1.5 text-right tabular text-text-1">
        {last != null ? formatNumber(last, 2) : <Dash />}
        {live != null && <span className="ml-1 text-[10px] text-state-demo">{quote?.is_demo ? "demo" : "live"}</span>}
      </td>
      <td className="px-3 py-1.5 text-right"><Money value={unreal} signed /></td>
      <td className="px-3 py-1.5 text-right"><Money value={num(p.realized_pnl)} signed /></td>
      <td className="px-3 py-1.5 tabular text-text-2">{formatDateTime(p.opened_at)}</td>
      <td className="px-3 py-1.5 tabular text-text-2">{p.closed_at ? formatDateTime(p.closed_at) : <span className="text-up">open</span>}</td>
    </tr>
  );
}

export function PositionsTable({ positions, isPending }: { positions: PaperPosition[] | undefined; isPending?: boolean }) {
  if (isPending) return <Skeleton className="m-3 h-20" />;
  if (!positions || positions.length === 0) return <EmptyState title="No positions" description="Positions open when a paper order fills." className="m-3" />;
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-3">
        <tr className="border-b border-border">
          <th className="px-3 py-1.5 text-left font-medium">Symbol</th>
          <th className="px-3 py-1.5 text-left font-medium">Product</th>
          <th className="px-3 py-1.5 text-right font-medium">Qty</th>
          <th className="px-3 py-1.5 text-right font-medium">Avg</th>
          <th className="px-3 py-1.5 text-right font-medium">Last</th>
          <th className="px-3 py-1.5 text-right font-medium">Unrealized</th>
          <th className="px-3 py-1.5 text-right font-medium">Realized</th>
          <th className="px-3 py-1.5 text-left font-medium">Opened</th>
          <th className="px-3 py-1.5 text-left font-medium">Closed</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <Row key={p.id} p={p} />
        ))}
      </tbody>
    </table>
  );
}
