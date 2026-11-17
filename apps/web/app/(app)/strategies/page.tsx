import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Strategy Center" subtitle="Ships in Phase 5" className="min-h-64">
      <PhasePlaceholder phase={5} what="Natural-language builder, visual builder, library, versions, approvals" />
    </PanelCard>
  );
}
