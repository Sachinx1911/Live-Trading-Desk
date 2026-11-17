import { DataStateBadge, Dash, PanelCard, PhasePlaceholder } from "@/components/design";
import { IndexCard } from "@/components/dashboard/IndexCard";
import { ProviderStatusPanel } from "@/components/dashboard/ProviderStatusPanel";

export default function DashboardPage() {
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-12 grid grid-cols-3 gap-3">
        <IndexCard symbol="NIFTY 50" name="NSE · Index" />
        <IndexCard symbol="BANKNIFTY" name="NSE · Index" />
        <IndexCard symbol="SENSEX" name="BSE · Index" reason="BSE adapter ships in Phase 9" />
      </div>

      <PanelCard
        title="Market chart"
        className="col-span-12 min-h-72 xl:col-span-8"
        actions={<DataStateBadge state="disconnected" />}
      >
        <PhasePlaceholder phase={2} what="Live and historical charting" />
      </PanelCard>

      <div className="col-span-12 flex flex-col gap-3 xl:col-span-4">
        <ProviderStatusPanel />
        <PanelCard title="Broker session">
          <div className="flex items-center justify-between">
            <p className="text-xs text-text-secondary">No broker connected</p>
            <DataStateBadge state="disconnected" detail="Phase 2" />
          </div>
        </PanelCard>
        <PanelCard title="Multi-market status">
          <ul className="text-xs">
            <li className="flex items-center justify-between py-1">
              <span className="text-text-primary">NSE</span>
              <span className="text-text-muted">Asia/Kolkata · 09:15–15:30</span>
            </li>
          </ul>
        </PanelCard>
      </div>

      <PanelCard title="Daily P&L" className="col-span-12 md:col-span-6 xl:col-span-3" actions={<DataStateBadge state="disconnected" />}>
        <Dash className="text-2xl font-semibold" />
        <p className="mt-1 text-[11px] text-text-muted">Paper and live accounts arrive in Phase 3.</p>
      </PanelCard>
      <PanelCard title="Win rate" className="col-span-12 md:col-span-6 xl:col-span-3" actions={<DataStateBadge state="disconnected" />}>
        <Dash className="text-2xl font-semibold" />
        <p className="mt-1 text-[11px] text-text-muted">Computed from closed trades only.</p>
      </PanelCard>
      <PanelCard title="Portfolio overview" className="col-span-12 xl:col-span-6">
        <PhasePlaceholder phase={3} what="Capital, margin and exposure" />
      </PanelCard>

      <PanelCard title="Active strategies" className="col-span-12 md:col-span-6 xl:col-span-4">
        <PhasePlaceholder phase={3} what="Strategy activations" />
      </PanelCard>
      <PanelCard title="Running trades" className="col-span-12 md:col-span-6 xl:col-span-4">
        <PhasePlaceholder phase={3} what="Open positions and orders" />
      </PanelCard>
      <PanelCard title="Strategy approval queue" className="col-span-12 xl:col-span-4">
        <PhasePlaceholder phase={5} what="Candidate versions awaiting your approval" />
      </PanelCard>

      <PanelCard title="AI market insights" className="col-span-12 md:col-span-6 xl:col-span-4">
        <PhasePlaceholder phase={6} what="Morning brief and regime commentary" />
      </PanelCard>
      <PanelCard title="AI research activity" className="col-span-12 md:col-span-6 xl:col-span-4">
        <PhasePlaceholder phase={6} what="Research jobs and candidates" />
      </PanelCard>
      <PanelCard title="AI learning insights" className="col-span-12 xl:col-span-4">
        <PhasePlaceholder phase={6} what="Trade reviews and improvement hypotheses" />
      </PanelCard>
    </div>
  );
}
