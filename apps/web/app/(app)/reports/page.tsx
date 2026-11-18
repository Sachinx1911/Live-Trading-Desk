"use client";

import { useMemo, useState } from "react";
import { EmptyState, Money, PanelCard } from "@/components/design";
import { AccountPicker } from "@/components/trading/AccountPicker";
import { TradesTable } from "@/components/trading/TradesTable";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePaperTrades } from "@/lib/api/trading";
import { formatNumber, IST } from "@/lib/format";
import { num } from "@/lib/ws/useMarket";

function istDay(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: IST, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}

export default function ReportsPage() {
  const { accountId, account } = usePaperAccount();
  const { data, isPending } = usePaperTrades(accountId, 2000);
  const [frm, setFrm] = useState("");
  const [to, setTo] = useState("");
  const trades = useMemo(
    () => (data ?? []).filter((t) => { const d = istDay(t.exit_at); return (!frm || d >= frm) && (!to || d <= to); }),
    [data, frm, to],
  );
  const daily = useMemo(() => {
    const m = new Map<string, { pnl: number; trades: number; wins: number; fees: number }>();
    for (const t of trades) {
      const d = istDay(t.exit_at);
      const row = m.get(d) ?? { pnl: 0, trades: 0, wins: 0, fees: 0 };
      row.pnl += num(t.net_pnl) ?? 0;
      row.trades += 1;
      row.wins += (num(t.net_pnl) ?? 0) > 0 ? 1 : 0;
      row.fees += num(t.costs) ?? 0;
      m.set(d, row);
    }
    return [...m.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [trades]);
  const total = trades.reduce((s, t) => s + (num(t.net_pnl) ?? 0), 0);
  const wins = trades.filter((t) => (num(t.net_pnl) ?? 0) > 0).length;

  return (
    <div className="grid grid-cols-12 gap-3">
      <PanelCard
        title="Trading journal"
        subtitle={account ? `${account.name} · paper · every closed round trip, with reasons` : "Paper trades"}
        className="col-span-12"
        actions={
          <div className="flex items-end gap-2">
            <div className="flex flex-col gap-1"><Label htmlFor="rp-frm" className="text-[10px]">From</Label><Input id="rp-frm" type="date" value={frm} onChange={(e) => setFrm(e.target.value)} className="h-7 text-xs" /></div>
            <div className="flex flex-col gap-1"><Label htmlFor="rp-to" className="text-[10px]">To</Label><Input id="rp-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-7 text-xs" /></div>
            <AccountPicker />
          </div>
        }
      >
        <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div><p className="text-[10px] uppercase text-text-muted">Trades</p><p className="tabular text-lg font-semibold">{formatNumber(trades.length)}</p></div>
          <div><p className="text-[10px] uppercase text-text-muted">Win rate</p><p className="tabular text-lg font-semibold">{trades.length ? `${((wins / trades.length) * 100).toFixed(1)}%` : "—"}</p></div>
          <div><p className="text-[10px] uppercase text-text-muted">Net P&L</p><Money value={trades.length ? total : null} signed className="text-lg font-semibold" /></div>
          <div><p className="text-[10px] uppercase text-text-muted">Expectancy / trade</p><Money value={trades.length ? total / trades.length : null} signed className="text-lg font-semibold" /></div>
        </div>
        <div className="overflow-x-auto rounded-sm border border-border-subtle">
          <TradesTable trades={trades} isPending={isPending} />
        </div>
      </PanelCard>
      <PanelCard title="Daily P&L" subtitle="Computed from closed trades (IST days)" className="col-span-12 xl:col-span-6" bodyClassName="p-0">
        {daily.length === 0 ? (
          <EmptyState title="No closed trades in range" className="m-3" />
        ) : (
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-text-muted"><tr className="border-b border-border-subtle"><th className="px-3 py-1.5 text-left font-medium">Day</th><th className="px-3 py-1.5 text-right font-medium">Trades</th><th className="px-3 py-1.5 text-right font-medium">Wins</th><th className="px-3 py-1.5 text-right font-medium">Fees</th><th className="px-3 py-1.5 text-right font-medium">Net</th></tr></thead>
            <tbody>
              {daily.map(([d, r]) => (
                <tr key={d} className="border-b border-border-subtle/60"><td className="px-3 py-1 tabular">{d}</td><td className="px-3 py-1 text-right tabular">{r.trades}</td><td className="px-3 py-1 text-right tabular">{r.wins}</td><td className="px-3 py-1 text-right"><Money value={r.fees} muted /></td><td className="px-3 py-1 text-right"><Money value={r.pnl} signed /></td></tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>
    </div>
  );
}
