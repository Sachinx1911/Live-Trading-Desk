import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="AI Trading Hub" subtitle="Ships in Phase 6" className="min-h-64">
      <PhasePlaceholder phase={6} what="Market analyst agent, trade setups and explanations" />
    </PanelCard>
  );
}
