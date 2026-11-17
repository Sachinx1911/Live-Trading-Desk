import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <PanelCard title="Backtesting" subtitle="Ships in Phase 4" className="min-h-64">
      <PhasePlaceholder phase={4} what="Backtest jobs, equity curve, drawdown, trade list, optimisation" />
    </PanelCard>
  );
}
