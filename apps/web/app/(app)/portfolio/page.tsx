"use client";

import { DataStateBadge, EmptyState, ModeTag, PanelCard, PhasePlaceholder } from "@/components/design";
import { AccountPicker } from "@/components/trading/AccountPicker";
import { KpiTiles } from "@/components/trading/KpiTiles";
import { PositionsTable } from "@/components/trading/PositionsTable";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { usePaperPositions } from "@/lib/api/trading";
import { useMarketSubscription } from "@/lib/ws/useMarket";

export default function PortfolioPage() {
  const { account, accountId, isPending } = usePaperAccount();
  const pos = usePaperPositions(accountId);
  useMarketSubscription((pos.data ?? []).map((p) => p.instrument_id));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">Portfolio <ModeTag mode="paper" /></h2>
        <AccountPicker />
      </div>
      {account ? <KpiTiles account={account} /> : isPending ? null : <EmptyState title="No paper account" description="Create one on the Paper Trading page." />}
      <PanelCard title="Equity curve" actions={<DataStateBadge state="historical" detail="snapshots" />}>
        <PhasePlaceholder phase={4} what="Equity curve and drawdown charts from portfolio snapshots" />
      </PanelCard>
      <PanelCard title="Open positions" bodyClassName="overflow-x-auto p-0">
        <PositionsTable positions={pos.data} isPending={pos.isPending && accountId != null} />
      </PanelCard>
      <PanelCard title="Live account">
        <EmptyState title="No live account" description="Live trading is disabled until Phase 10 validation." />
      </PanelCard>
    </div>
  );
}
