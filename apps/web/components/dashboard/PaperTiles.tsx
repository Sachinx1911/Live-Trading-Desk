"use client";

import Link from "next/link";
import { DataStateBadge, Dash, EmptyState, Money, PanelCard } from "@/components/design";
import { StatusChip } from "@/components/trading/StatusChip";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { useActivations, usePaperPositions, usePaperRiskLimits, usePaperTrades } from "@/lib/api/trading";
import { formatNumber, IST } from "@/lib/format";
import { num } from "@/lib/ws/useMarket";

function istDay(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}

/** Dashboard tiles backed by the first/selected paper account. Explicit empty states, no defaults. */
export function PaperTiles() {
  const { account, accountId } = usePaperAccount();
  const { data: activations } = useActivations(accountId);
  const { data: positions } = usePaperPositions(accountId);
  const { data: trades } = usePaperTrades(accountId, 500);
  const { data: limits } = usePaperRiskLimits(accountId);
  const today = istDay(new Date().toISOString());
  const todays = (trades ?? []).filter((t) => istDay(t.exit_at) === today);
  const dayPnl = account ? todays.reduce((s, t) => s + (num(t.net_pnl) ?? 0), 0) : null;
  const wins = todays.filter((t) => (num(t.net_pnl) ?? 0) > 0).length;
  const allWins = (trades ?? []).filter((t) => (num(t.net_pnl) ?? 0) > 0).length;
  const cap = num(account?.initial_capital);
  const dailyLimit = cap != null && limits ? (cap * limits.limits.max_daily_loss_pct) / 100 : null;
  const used = dailyLimit && dayPnl != null && dayPnl < 0 ? Math.min(100, (-dayPnl / dailyLimit) * 100) : 0;
  const badge = <DataStateBadge state={account ? "demo" : "disconnected"} detail={account ? "paper" : "no account"} />;

  return (
    <>
      <PanelCard title="Daily P&L" className="col-span-12 md:col-span-6 xl:col-span-3" actions={badge}>
        <Money value={account && trades ? dayPnl : null} signed className="text-2xl font-semibold" />
        <p className="mt-1 text-[11px] text-text-muted">{account ? `${todays.length} closed trade(s) today · ${wins} won` : "Create a paper account to start."}</p>
      </PanelCard>
      <PanelCard title="Win rate" className="col-span-12 md:col-span-6 xl:col-span-3" actions={badge}>
        {trades && trades.length > 0 ? <span className="tabular text-2xl font-semibold">{((allWins / trades.length) * 100).toFixed(1)}%</span> : <Dash className="text-2xl font-semibold" />}
        <p className="mt-1 text-[11px] text-text-muted">{trades ? `${formatNumber(trades.length)} closed trades, all time` : "Computed from closed trades only."}</p>
      </PanelCard>
      <PanelCard title="Risk · daily loss used" className="col-span-12 xl:col-span-6" actions={<Link href="/settings/risk" className="text-[11px] text-accent-cyan">limits</Link>}>
        {account && limits ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-text-secondary">{used.toFixed(0)}% of <Money value={dailyLimit} whole muted /> ({limits.limits.max_daily_loss_pct}% of capital)</span>
              <span className="tabular text-text-primary">equity <Money value={num(account.equity)} /></span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-sm bg-panel-raised"><div className={used >= 90 ? "h-full bg-pnl-negative" : used >= 50 ? "h-full bg-state-delayed" : "h-full bg-pnl-positive"} style={{ width: `${used}%` }} /></div>
            <p className="text-[11px] text-text-muted">Entries stop automatically at 100%; exits always allowed.</p>
          </div>
        ) : (
          <EmptyState title="No paper account" />
        )}
      </PanelCard>
      <PanelCard title="Active strategies" className="col-span-12 md:col-span-6 xl:col-span-4" bodyClassName="p-0" actions={<Link href="/paper" className="text-[11px] text-accent-cyan">paper</Link>}>
        {!activations || activations.length === 0 ? (
          <EmptyState title="Nothing running" description="Activate a strategy version on a paper account." className="m-3" />
        ) : (
          <ul className="text-xs">
            {activations.map((a) => (
              <li key={a.id} className="flex items-center justify-between border-b border-border-subtle/60 px-3 py-1.5 last:border-0">
                <span className="truncate text-text-primary">{a.strategy_name} <span className="text-text-muted">v{a.version_no} · {a.symbol ?? `#${a.instrument_id}`}</span></span>
                <StatusChip value={a.status} />
              </li>
            ))}
          </ul>
        )}
      </PanelCard>
      <PanelCard title="Running trades" className="col-span-12 md:col-span-6 xl:col-span-4" bodyClassName="p-0" actions={<Link href="/paper/positions" className="text-[11px] text-accent-cyan">positions</Link>}>
        {!positions || positions.length === 0 ? (
          <EmptyState title="No open positions" className="m-3" />
        ) : (
          <ul className="text-xs">
            {positions.map((p) => (
              <li key={p.id} className="flex items-center justify-between border-b border-border-subtle/60 px-3 py-1.5 last:border-0">
                <span className="text-text-primary">{p.symbol ?? `#${p.instrument_id}`} <span className={p.quantity > 0 ? "text-pnl-positive" : "text-pnl-negative"}>{p.quantity > 0 ? "+" : ""}{formatNumber(p.quantity)}</span></span>
                <Money value={num(p.unrealized_pnl)} signed />
              </li>
            ))}
          </ul>
        )}
      </PanelCard>
    </>
  );
}
