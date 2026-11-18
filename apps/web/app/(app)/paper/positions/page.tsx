"use client";

import { useState } from "react";
import { PanelCard } from "@/components/design";
import { PaperHeader } from "@/components/trading/PaperHeader";
import { PositionsTable } from "@/components/trading/PositionsTable";
import { TradesTable } from "@/components/trading/TradesTable";
import { usePaperPositions, usePaperTrades } from "@/lib/api/trading";
import { useMarketSubscription } from "@/lib/ws/useMarket";

function Positions({ accountId }: { accountId: number }) {
  const [closed, setClosed] = useState(false);
  const pos = usePaperPositions(accountId, closed);
  const trades = usePaperTrades(accountId);
  useMarketSubscription((pos.data ?? []).filter((p) => !p.closed_at).map((p) => p.instrument_id));
  return (
    <>
      <PanelCard
        title="Positions"
        bodyClassName="overflow-x-auto p-0"
        actions={
          <label className="flex items-center gap-1 text-[11px] text-text-secondary">
            <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} /> include closed
          </label>
        }
      >
        <PositionsTable positions={pos.data} isPending={pos.isPending} />
      </PanelCard>
      <PanelCard title="Closed trades" subtitle="Round trips with Indian charges applied" bodyClassName="overflow-x-auto p-0">
        <TradesTable trades={trades.data} isPending={trades.isPending} />
      </PanelCard>
    </>
  );
}

export default function PaperPositionsPage() {
  return <PaperHeader>{(id) => <Positions accountId={id} />}</PaperHeader>;
}
