import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Portfolio & Analytics" subtitle="Ships in Phase 3" className="min-h-64">
      <PhasePlaceholder phase={3} what="Capital, positions, strategy-wise and instrument-wise returns" />
    </PanelCard>
  );
}
