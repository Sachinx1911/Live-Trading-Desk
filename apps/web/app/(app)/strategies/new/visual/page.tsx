import Link from "next/link";
import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Visual Strategy Builder" subtitle="Ships in Phase 5" className="min-h-64" actions={<Link href="/strategies" className="text-[11px] text-accent-cyan">Back to library</Link>}>
      <PhasePlaceholder phase={5} what="Drag-and-drop indicators, AND/OR condition trees, stop/target and sizing" />
    </PanelCard>
  );
}
