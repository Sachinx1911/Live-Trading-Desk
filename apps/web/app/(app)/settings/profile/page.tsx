import { PanelCard, PhasePlaceholder } from "@/components/design";
import { ThemeSegmented } from "@/components/layout/ThemeControl";

export default function Page() {
  return (
    <div className="flex flex-col gap-px">
      <PanelCard title="Appearance" subtitle="Dark follows the TradingView reference; Light mirrors it on white">
        <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3">
          <div>
            <p className="text-[14px] text-text-1">Theme</p>
            <p className="text-[12px] text-text-3">Stored on this browser. System follows your OS setting.</p>
          </div>
          <ThemeSegmented />
        </div>
      </PanelCard>
      <PanelCard title="Profile" subtitle="Ships in Phase 10" className="min-h-64">
        <PhasePlaceholder phase={10} what="Display name and locale" />
      </PanelCard>
    </div>
  );
}
