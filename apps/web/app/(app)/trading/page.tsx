"use client";

import Link from "next/link";
import { DataStateBadge, EmptyState, ModeTag, Money, PanelCard } from "@/components/design";
import { KillSwitchPanel } from "@/components/trading/KillSwitchPanel";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { useActivations } from "@/lib/api/trading";
import { num } from "@/lib/ws/useMarket";

export default function TradingPage() {
  const { account, accountId } = usePaperAccount();
  const { data: activations } = useActivations(accountId);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 md:grid-cols-2">
        <PanelCard title={<span className="flex items-center gap-2">Paper <ModeTag mode="paper" /></span>} actions={<DataStateBadge state="demo" detail="virtual money" />}>
          {account ? (
            <div className="flex flex-col gap-2 text-xs">
              <div className="flex items-baseline justify-between">
                <span className="text-text-secondary">{account.name}</span>
                <Money value={num(account.equity)} className="text-lg font-semibold" />
              </div>
              <div className="flex justify-between text-text-secondary">
                <span>Running strategies</span>
                <span className="tabular text-text-primary">{activations?.length ?? 0}</span>
              </div>
              <div className="flex justify-between text-text-secondary">
                <span>Open positions</span>
                <span className="tabular text-text-primary">{account.open_positions}</span>
              </div>
              <div className="flex gap-3 pt-1 text-accent-cyan">
                <Link href="/paper">Overview</Link>
                <Link href="/paper/orders">Orders</Link>
                <Link href="/paper/positions">Positions</Link>
                <Link href="/settings/risk">Risk limits</Link>
              </div>
            </div>
          ) : (
            <EmptyState title="No paper account" description="Create one on the Paper Trading page." />
          )}
        </PanelCard>
        <PanelCard title={<span className="flex items-center gap-2">Live <ModeTag mode="live" /></span>} actions={<DataStateBadge state="disconnected" detail="disabled" />}>
          <EmptyState
            title="Live trading disabled (LIVE_TRADING_ENABLED=false)"
            description="The live order gateway refuses every order until Phase 10 validation: approved version, broker session, risk pass, loss limits, kill switch off."
          />
        </PanelCard>
      </div>
      <KillSwitchPanel accountId={accountId} />
    </div>
  );
}
