import Link from "next/link";
import { AiBadge, PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title={<span className="flex items-center gap-2">Natural-language builder <AiBadge /></span>} subtitle="Ships in Phase 5 · Marathi, Hindi, English" className="min-h-64" actions={<Link href="/strategies" className="text-[11px] text-accent-cyan">Back to library</Link>}>
      <PhasePlaceholder phase={5} what="Describe a strategy in your language; the AI drafts the DSL and asks for what is missing" />
    </PanelCard>
  );
}
