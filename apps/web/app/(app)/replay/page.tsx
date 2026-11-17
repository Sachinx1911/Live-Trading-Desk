import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Historical Replay" subtitle="Ships in Phase 4" className="min-h-64">
      <PhasePlaceholder phase={4} what="Replay sessions with play, pause, speed and step controls" />
    </PanelCard>
  );
}
