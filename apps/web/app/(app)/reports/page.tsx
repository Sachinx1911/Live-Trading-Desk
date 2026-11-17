import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Reports" subtitle="Ships in Phase 3" className="min-h-64">
      <PhasePlaceholder phase={3} what="Daily, weekly and monthly performance; trading journal exports" />
    </PanelCard>
  );
}
