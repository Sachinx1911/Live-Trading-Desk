import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Market Data" subtitle="Ships in Phase 2" className="min-h-64">
      <PhasePlaceholder phase={2} what="Watchlist, chart, option chain, provider management" />
    </PanelCard>
  );
}
