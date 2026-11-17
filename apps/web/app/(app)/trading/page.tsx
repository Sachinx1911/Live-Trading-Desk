import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Trading" subtitle="Ships in Phase 3" className="min-h-64">
      <PhasePlaceholder phase={3} what="Trading overview across paper and live accounts" />
    </PanelCard>
  );
}
