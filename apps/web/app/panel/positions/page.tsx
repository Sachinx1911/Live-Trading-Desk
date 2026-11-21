"use client";

import { Suspense } from "react";
import { Money } from "@/components/design";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { PositionsTable } from "@/components/trading/PositionsTable";
import { ApiRequestError } from "@/lib/api/client";
import { usePaperAccount, usePaperPositions } from "@/lib/api/trading";
import { fullPageUrl } from "@/lib/panels";
import { useMarketSubscription, num } from "@/lib/ws/useMarket";

function Kpi({ label, value, signed, sub }: { label: string; value: number | null; signed?: boolean; sub?: string }) {
  return (
    <div className="min-w-0 bg-pane px-3 py-2">
      <p className="hud-label truncate text-text-3">{label}</p>
      <Money value={value} signed={signed} className="block truncate font-mono text-[clamp(16px,2.6vw,32px)] leading-tight font-semibold" />
      {sub && <p className="truncate text-[11px] text-text-3">{sub}</p>}
    </div>
  );
}

function PositionsPanel() {
  const { values, errors } = usePanelParams("positions");
  const accountId = errors.length || values.account == null ? null : Number(values.account);
  const closed = values.closed === "1";
  const account = usePaperAccount(accountId);
  const pos = usePaperPositions(account.data ? accountId : null, closed);
  useMarketSubscription((pos.data ?? []).filter((p) => !p.closed_at).map((p) => p.instrument_id));

  const a = account.data;
  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="positions"
      subtitle={a ? `${a.name} · #${a.id}${closed ? " · incl. closed" : ""}` : values.account ? `account #${values.account}` : undefined}
      // Paper P&L is simulated: always marked as such (same convention as the paper KPI tiles).
      state={a ? "demo" : undefined}
      stateDetail="paper"
      fullHref={fullPageUrl("positions")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="positions" errors={errors} />);
  if (account.isPending) return frame(<PanelMessage title="Loading paper account…" />);
  if (account.error instanceof ApiRequestError && account.error.status === 404)
    return frame(<PanelMessage tone="error" title={`account: paper account #${accountId} not found`} description="List your paper accounts on the Paper page." />);
  if (account.isError || !a) return frame(<PanelMessage tone="error" title="Cannot reach the API" description="Paper account data is unavailable; nothing is shown in its place." />);

  const eq = num(a.equity);
  const cap = num(a.initial_capital);
  const ret = eq != null && cap ? ((eq - cap) / cap) * 100 : null;
  return frame(
    <div className="flex min-h-full flex-col">
      <div className="grid shrink-0 grid-cols-2 gap-px border-b border-border bg-border sm:grid-cols-4">
        <Kpi label="Equity" value={eq} sub={ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}% vs capital` : undefined} />
        <Kpi label="Unrealized" value={num(a.unrealized_pnl)} signed sub={`${a.open_positions} open`} />
        <Kpi label="Realized (total)" value={num(a.realized_pnl_total)} signed />
        <Kpi label="Cash" value={num(a.cash)} />
      </div>
      <div className="min-h-0 flex-1 overflow-x-auto">
        <PositionsTable positions={pos.data} isPending={pos.isPending} />
      </div>
    </div>,
  );
}

export default function PositionsPanelPage() {
  return (
    <Suspense>
      <PositionsPanel />
    </Suspense>
  );
}
