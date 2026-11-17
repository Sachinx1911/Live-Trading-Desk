import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Users" subtitle="Ships in Phase 10" className="min-h-64">
      <PhasePlaceholder phase={10} what="Operators and roles" />
    </PanelCard>
  );
}
