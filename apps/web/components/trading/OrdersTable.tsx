"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";
import { Dash, EmptyState, Money } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { PaperOrder } from "@/lib/api/generated";
import { usePaperOrderEvents } from "@/lib/api/trading";
import { formatDateTime, formatNumber, formatTime } from "@/lib/format";
import { num } from "@/lib/ws/useMarket";
import { SideText, StatusChip } from "./StatusChip";

function EventsRow({ orderId }: { orderId: number }) {
  const { data, isPending } = usePaperOrderEvents(orderId);
  return (
    <tr className="border-b border-border-subtle/60 bg-panel-raised/60">
      <td colSpan={11} className="px-6 py-2">
        {isPending ? (
          <Skeleton className="h-8" />
        ) : !data || data.length === 0 ? (
          <p className="text-[11px] text-text-muted">No events recorded.</p>
        ) : (
          <ol className="flex flex-col gap-1 text-[11px]">
            {data.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2">
                <span className="tabular text-text-muted">{formatTime(e.ts)}</span>
                <StatusChip value={e.from_status} /> → <StatusChip value={e.to_status} />
                {e.fill_qty != null && (
                  <span className="tabular text-text-primary">
                    {formatNumber(e.fill_qty)} @ {e.fill_px ? formatNumber(Number(e.fill_px), 2) : "—"}
                  </span>
                )}
                <span className="text-text-secondary">{e.reason}</span>
                <span className="text-text-muted">· {e.source}</span>
              </li>
            ))}
          </ol>
        )}
      </td>
    </tr>
  );
}

export function OrdersTable({ orders, isPending }: { orders: PaperOrder[] | undefined; isPending?: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  if (isPending) return <Skeleton className="m-3 h-24" />;
  if (!orders || orders.length === 0) return <EmptyState title="No orders yet" description="Orders appear here when a running strategy sends a signal that passes risk checks." className="m-3" />;
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-muted">
        <tr className="border-b border-border-subtle">
          <th className="w-6 px-2 py-1.5" />
          <th className="px-3 py-1.5 text-left font-medium">Time</th>
          <th className="px-3 py-1.5 text-left font-medium">Symbol</th>
          <th className="px-3 py-1.5 text-left font-medium">Side</th>
          <th className="px-3 py-1.5 text-left font-medium">Type</th>
          <th className="px-3 py-1.5 text-right font-medium">Qty / filled</th>
          <th className="px-3 py-1.5 text-right font-medium">Avg fill</th>
          <th className="px-3 py-1.5 text-left font-medium">Status</th>
          <th className="px-3 py-1.5 text-right font-medium">Costs</th>
          <th className="px-3 py-1.5 text-right font-medium">Bid / ask @ place</th>
          <th className="px-3 py-1.5 text-left font-medium">Reason</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((o) => (
          <Fragment key={o.id}>
            <tr className="border-b border-border-subtle/60 hover:bg-panel-raised/40">
              <td className="px-2 py-1.5">
                <button type="button" aria-label="Toggle events" onClick={() => setOpen(open === o.id ? null : o.id)} className="text-text-muted">
                  {open === o.id ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                </button>
              </td>
              <td className="px-3 py-1.5 tabular text-text-secondary">{formatDateTime(o.submitted_at)}</td>
              <td className="px-3 py-1.5 text-text-primary">{o.symbol ?? `#${o.instrument_id}`}</td>
              <td className="px-3 py-1.5"><SideText side={o.side} /></td>
              <td className="px-3 py-1.5 uppercase text-text-secondary">{o.order_type.replace("_", " ")} · {o.product}</td>
              <td className="px-3 py-1.5 text-right tabular text-text-primary">{formatNumber(o.quantity)} / {formatNumber(o.filled_qty)}</td>
              <td className="px-3 py-1.5 text-right tabular text-text-primary">{o.avg_fill_price ? formatNumber(Number(o.avg_fill_price), 2) : <Dash />}</td>
              <td className="px-3 py-1.5"><StatusChip value={o.status} /></td>
              <td className="px-3 py-1.5 text-right"><Money value={num(o.costs)} muted /></td>
              <td className="px-3 py-1.5 text-right tabular text-text-secondary">
                {o.bid_at_place ? formatNumber(Number(o.bid_at_place), 2) : "—"} / {o.ask_at_place ? formatNumber(Number(o.ask_at_place), 2) : "—"}
              </td>
              <td className="max-w-64 truncate px-3 py-1.5 text-text-secondary" title={o.reason ?? ""}>{o.reason ?? <Dash />}</td>
            </tr>
            {open === o.id && <EventsRow orderId={o.id} />}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}
