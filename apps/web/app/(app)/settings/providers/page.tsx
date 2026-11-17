import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Data providers" subtitle="Ships in Phase 2" className="min-h-64">
      <PhasePlaceholder phase={2} what="Active provider, comparison mode and failover controls" />
    </PanelCard>
  );
}
