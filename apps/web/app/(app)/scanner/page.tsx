import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Market Scanner" subtitle="Ships in Phase 5" className="min-h-64">
      <PhasePlaceholder phase={5} what="Rule-based scans across the instrument universe" />
    </PanelCard>
  );
}
