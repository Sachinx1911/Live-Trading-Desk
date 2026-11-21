import { PanelCard, PhasePlaceholder } from "@/components/design";
import { MarketStrip } from "@/components/dashboard/MarketStrip";
import { BreadthTile } from "@/components/dashboard/BreadthTile";
import { BrokerSessionPanel } from "@/components/dashboard/BrokerSessionPanel";
import { PaperTiles } from "@/components/dashboard/PaperTiles";
import { RegimeTile } from "@/components/dashboard/RegimeTile";
import { ProviderStatusPanel } from "@/components/dashboard/ProviderStatusPanel";

export default function DashboardPage() {
  return (
    <div className="grid grid-cols-12 gap-3">
      <MarketStrip />

      <div className="col-span-12 flex flex-col gap-3 xl:col-span-4">
        <ProviderStatusPanel />
        <BrokerSessionPanel />
        <PanelCard title="Multi-market status">
          <ul className="text-xs">
            <li className="flex items-center justify-between py-1">
              <span className="text-text-1">NSE</span>
              <span className="text-text-3">Asia/Kolkata · 09:15–15:30</span>
            </li>
          </ul>
        </PanelCard>
      </div>

      <PaperTiles />

      <RegimeTile className="col-span-12 xl:col-span-4" />

      <BreadthTile className="col-span-12 md:col-span-6 xl:col-span-4" />

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
