"use client";

import { useEffect, useRef, useState } from "react";
import { Dash, EmptyState, Money } from "@/components/design";
import { SideText, StatusChip } from "@/components/trading/StatusChip";
import type { ReplayOverlayState, ReplayTrade } from "@/lib/api/generated";
import { formatNumber, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { num } from "@/lib/ws/useMarket";
import type { ReplayEvent, SeenTrade } from "./useReplayStream";

type Tab = "events" | "positions" | "trades" | "state";

const TH = "px-3 py-1.5 text-left font-medium";
const THR = "px-3 py-1.5 text-right font-medium";

function EventRow({ e }: { e: ReplayEvent }) {
  const t = <td className="w-24 px-3 py-1.5 tabular text-text-3">{formatTime(e.ts)}</td>;
  switch (e.kind) {
    case "signal":
      return (
        <tr className="border-b border-border/60">
          {t}
          <td className="px-3 py-1.5"><StatusChip value="signal" tone="info" /></td>
          <td className="px-3 py-1.5">
            <SideText side={e.data.side} /> <span className="text-text-2">{e.data.kind}</span>
            <span className="ml-2 tabular text-text-3">ref {formatNumber(Number(e.data.reference_price), 2)}</span>
            {e.data.stop_price && <span className="ml-2 tabular text-text-3">SL {formatNumber(Number(e.data.stop_price), 2)}</span>}
            {e.data.target_price && <span className="ml-2 tabular text-text-3">TP {formatNumber(Number(e.data.target_price), 2)}</span>}
            <div className="truncate text-text-2" title={e.data.reason}>{e.data.reason}</div>
          </td>
        </tr>
      );
    case "signal_rejected":
      return (
        <tr className="border-b border-border/60">
          {t}
          <td className="px-3 py-1.5"><StatusChip value="rejected" /></td>
          <td className="px-3 py-1.5">
            <span className="text-text-2">{e.data.kind} blocked by risk engine</span>
            <ul className="mt-0.5 list-disc pl-4 text-down">
              {e.data.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          </td>
        </tr>
      );
    case "order":
      return (
        <tr className="border-b border-border/60">
          {t}
          <td className="px-3 py-1.5"><StatusChip value={e.data.status} /></td>
          <td className="px-3 py-1.5">
            <SideText side={e.data.side} /> <span className="tabular">{formatNumber(e.data.quantity)}</span>{" "}
            <span className="text-text-2">{e.data.order_type}</span>
            {e.data.avg_fill_price && <span className="ml-2 tabular text-text-3">avg {formatNumber(Number(e.data.avg_fill_price), 2)}</span>}
            <span className="ml-2 font-mono text-[10px] text-text-3">{e.data.order_id.slice(0, 8)}</span>
          </td>
        </tr>
      );
    case "fill":
      return (
        <tr className="border-b border-border/60">
          {t}
          <td className="px-3 py-1.5"><StatusChip value="fill" tone="ok" /></td>
          <td className="px-3 py-1.5">
            <SideText side={e.data.side} /> <span className="tabular">{formatNumber(e.data.quantity)}</span> @{" "}
            <span className="tabular">{formatNumber(Number(e.data.price), 2)}</span>
            <span className="ml-2 tabular text-text-3">costs {formatNumber(Number(e.data.costs), 2)}</span>
          </td>
        </tr>
      );
  }
}

function EventsLog({ events, hasStrategy }: { events: ReplayEvent[]; hasStrategy: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);
  if (!hasStrategy) return <EmptyState title="No strategy attached" description="Start a replay with a strategy version to see its signals, risk decisions, orders and fills here." className="m-3" />;
  if (events.length === 0) return <EmptyState title="No events yet" description="Signals appear as the strategy evaluates each closed bar." className="m-3" />;
  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-pane text-[10px] uppercase tracking-wide text-text-3">
          <tr className="border-b border-border">
            <th className={TH}>Time</th>
            <th className={TH}>Event</th>
            <th className={TH}>Detail</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => <EventRow key={e.id} e={e} />)}
        </tbody>
      </table>
      <div ref={endRef} />
    </div>
  );
}

function Positions({ overlay, symbol }: { overlay: ReplayOverlayState | null; symbol: string }) {
  if (!overlay) return <EmptyState title="No strategy attached" className="m-3" />;
  const p = overlay.position;
  if (!p || p.quantity === 0) return <EmptyState title="Flat" description="No open position at the replay cursor." className="m-3" />;
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-3">
        <tr className="border-b border-border">
          <th className={TH}>Symbol</th>
          <th className={TH}>Side</th>
          <th className={THR}>Qty</th>
          <th className={THR}>Avg</th>
          <th className={THR}>Last</th>
          <th className={THR}>Unrealised</th>
          <th className={THR}>Realised</th>
        </tr>
      </thead>
      <tbody>
        <tr className="border-b border-border/60">
          <td className="px-3 py-1.5 text-text-1">{symbol}</td>
          <td className="px-3 py-1.5"><SideText side={p.quantity > 0 ? "buy" : "sell"} /></td>
          <td className="px-3 py-1.5 text-right tabular">{formatNumber(Math.abs(p.quantity))}</td>
          <td className="px-3 py-1.5 text-right tabular">{formatNumber(Number(p.avg_price), 2)}</td>
          <td className="px-3 py-1.5 text-right tabular">{p.last_price ? formatNumber(Number(p.last_price), 2) : <Dash />}</td>
          <td className="px-3 py-1.5 text-right"><Money value={num(p.unrealized_pnl)} signed /></td>
          <td className="px-3 py-1.5 text-right"><Money value={num(p.realized_pnl)} signed muted /></td>
        </tr>
      </tbody>
    </table>
  );
}

function Trades({ trades: seen, hasStrategy }: { trades: SeenTrade[]; hasStrategy: boolean }) {
  const trades: ReplayTrade[] = seen.map((t) => t.data);
  if (!hasStrategy) return <EmptyState title="No strategy attached" className="m-3" />;
  if (trades.length === 0) return <EmptyState title="No closed trades yet" description="A trade is recorded when the position returns to flat." className="m-3" />;
  const net = trades.reduce((a, t) => a + Number(t.net_pnl), 0);
  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-pane text-[10px] uppercase tracking-wide text-text-3">
          <tr className="border-b border-border">
            <th className={TH}>Side</th>
            <th className={THR}>Qty</th>
            <th className={TH}>Entry</th>
            <th className={THR}>Entry px</th>
            <th className={TH}>Exit</th>
            <th className={THR}>Exit px</th>
            <th className={THR}>Gross</th>
            <th className={THR}>Costs</th>
            <th className={THR}>Net</th>
            <th className={TH}>Reasons</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={`${t.entry_at}-${t.exit_at}-${i}`} className="border-b border-border/60">
              <td className="px-3 py-1.5"><SideText side={t.side} /></td>
              <td className="px-3 py-1.5 text-right tabular">{formatNumber(t.quantity)}</td>
              <td className="px-3 py-1.5 tabular text-text-2">{formatTime(t.entry_at)}</td>
              <td className="px-3 py-1.5 text-right tabular">{formatNumber(Number(t.entry_price), 2)}</td>
              <td className="px-3 py-1.5 tabular text-text-2">{formatTime(t.exit_at)}</td>
              <td className="px-3 py-1.5 text-right tabular">{formatNumber(Number(t.exit_price), 2)}</td>
              <td className="px-3 py-1.5 text-right"><Money value={num(t.gross_pnl)} signed muted /></td>
              <td className="px-3 py-1.5 text-right"><Money value={num(t.costs)} muted /></td>
              <td className="px-3 py-1.5 text-right"><Money value={num(t.net_pnl)} signed /></td>
              <td className="max-w-64 truncate px-3 py-1.5 text-text-2" title={`${t.entry_reason ?? ""} → ${t.exit_reason ?? ""}`}>
                {t.entry_reason ?? "—"} → {t.exit_reason ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="text-[11px]">
          <tr>
            <td className="px-3 py-1.5 text-text-3" colSpan={8}>{trades.length} closed trade{trades.length === 1 ? "" : "s"}</td>
            <td className="px-3 py-1.5 text-right"><Money value={net} signed /></td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border border-border bg-raised/40 px-3 py-2">
      <span className="text-[10px] uppercase tracking-wide text-text-3">{label}</span>
      <span className="tabular text-[14px] text-text-1">{value}</span>
    </div>
  );
}

function OverlayState({ overlay, warmupBars }: { overlay: ReplayOverlayState | null; warmupBars: number }) {
  if (!overlay) return <EmptyState title="No strategy attached" description="Cash and equity are tracked only when a strategy version runs on the replay." className="m-3" />;
  return (
    <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3">
      <Stat label="Equity" value={<Money value={num(overlay.equity)} />} />
      <Stat label="Cash" value={<Money value={num(overlay.cash)} />} />
      <Stat label="Realised" value={<Money value={num(overlay.realized)} signed />} />
      <Stat label="Unrealised" value={<Money value={num(overlay.unrealized)} signed />} />
      <Stat label="Closed trades" value={overlay.trades} />
      <Stat label="Engine state" value={<span className="text-[12px] text-text-2">{overlay.engine ?? "flat"}</span>} />
      <p className="col-span-full text-[11px] text-text-3">
        Virtual capital ₹1,00,000, spread-aware slippage, default risk limits. Warmed up on {warmupBars} strategy-timeframe bar{warmupBars === 1 ? "" : "s"} from the preceding sessions.
      </p>
    </div>
  );
}

export function ReplayPanels({
  events,
  trades,
  overlay,
  warmupBars,
  hasStrategy,
  symbol,
}: {
  events: ReplayEvent[];
  trades: SeenTrade[];
  overlay: ReplayOverlayState | null;
  warmupBars: number;
  hasStrategy: boolean;
  symbol: string;
}) {
  const [tab, setTab] = useState<Tab>("events");
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "events", label: "Events", count: events.length || undefined },
    { id: "positions", label: "Positions", count: overlay?.position && overlay.position.quantity !== 0 ? 1 : undefined },
    { id: "trades", label: "Trades", count: trades.length || undefined },
    { id: "state", label: "Equity" },
  ];
  return (
    <div className="flex min-w-0 flex-col">
      <div role="tablist" className="flex items-center gap-0.5 border-b border-border px-2 py-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-[var(--r-pill)] px-[11px] text-[13px] transition-colors",
              tab === t.id ? "bg-raised text-text-1" : "text-text-3 hover:bg-hover hover:text-text-2",
            )}
          >
            {t.label}
            {t.count != null && <span className="tabular text-[11px] text-text-3">{t.count}</span>}
          </button>
        ))}
      </div>
      <div className="min-h-32">
        {tab === "events" && <EventsLog events={events} hasStrategy={hasStrategy} />}
        {tab === "positions" && <Positions overlay={overlay} symbol={symbol} />}
        {tab === "trades" && <Trades trades={trades} hasStrategy={hasStrategy} />}
        {tab === "state" && <OverlayState overlay={overlay} warmupBars={warmupBars} />}
      </div>
    </div>
  );
}
