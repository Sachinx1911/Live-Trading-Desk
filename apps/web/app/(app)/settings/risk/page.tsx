import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Risk limits" subtitle="Ships in Phase 3" className="min-h-64">
      <PhasePlaceholder phase={3} what="Per-trade risk, daily/weekly loss limits, kill switch" />
    </PanelCard>
  );
}
