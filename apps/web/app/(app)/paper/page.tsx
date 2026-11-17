import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Paper Trading" subtitle="Ships in Phase 3" className="min-h-64">
      <PhasePlaceholder phase={3} what="Virtual accounts, orders, positions, realistic fills" />
    </PanelCard>
  );
}
