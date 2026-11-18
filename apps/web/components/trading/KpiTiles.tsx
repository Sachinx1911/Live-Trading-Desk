import { DataStateBadge, Money, PanelCard } from "@/components/design";
import type { PaperAccount } from "@/lib/api/generated";
import { num } from "@/lib/ws/useMarket";

export function KpiTiles({ account }: { account: PaperAccount }) {
  const eq = num(account.equity);
  const cap = num(account.initial_capital);
  const ret = eq != null && cap ? ((eq - cap) / cap) * 100 : null;
  const tiles: { label: string; value: number | null; signed?: boolean; sub?: string }[] = [
    { label: "Equity", value: eq, sub: ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}% vs capital` : undefined },
    { label: "Cash", value: num(account.cash) },
    { label: "Unrealized P&L", value: num(account.unrealized_pnl), signed: true },
    { label: "Realized P&L (total)", value: num(account.realized_pnl_total), signed: true },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
      {tiles.map((t) => (
        <PanelCard key={t.label} title={t.label} actions={<DataStateBadge state="demo" detail="paper" />}>
          <Money value={t.value} signed={t.signed} className="text-xl font-semibold" />
          {t.sub && <p className="mt-1 text-[11px] text-text-3">{t.sub}</p>}
        </PanelCard>
      ))}
      <PanelCard title="Open positions">
        <span className="tabular text-xl font-semibold text-text-1">{account.open_positions}</span>
        <p className="mt-1 text-[11px] text-text-3">High-water mark <Money value={num(account.equity_hwm)} whole muted /></p>
      </PanelCard>
    </div>
  );
}
