import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Tools" subtitle="Ships in Phase 2" className="min-h-64">
      <PhasePlaceholder phase={2} what="Data import, instrument lookup, cost calculator" />
    </PanelCard>
  );
}
