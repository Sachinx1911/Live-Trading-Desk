import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="AI Learning" subtitle="Ships in Phase 6" className="min-h-64">
      <PhasePlaceholder phase={6} what="Trade reviews, winning/losing analysis, candidate versions" />
    </PanelCard>
  );
}
