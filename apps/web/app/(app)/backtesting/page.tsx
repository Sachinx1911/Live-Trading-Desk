"use client";

import { SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { PanelCard } from "@/components/design";
import { BacktestForm } from "@/components/backtests/BacktestForm";
import { JobsTable } from "@/components/backtests/JobsTable";
import { useBacktests } from "@/lib/api/backtests";

function NewBacktestCard() {
  const params = useSearchParams();
  const preset = params.get("strategy");
  return (
    <PanelCard title="New backtest" subtitle="Reproducible: config + seed + data hash are frozen with the result" className="col-span-12 xl:col-span-4">
      <BacktestForm presetStrategyId={preset ? Number(preset) : undefined} />
    </PanelCard>
  );
}

export default function BacktestingPage() {
  const { data, isPending } = useBacktests();
  return (
    <div className="grid grid-cols-12 gap-3">
      <Suspense fallback={null}>
        <NewBacktestCard />
      </Suspense>
      <PanelCard
        title="Backtest jobs"
        subtitle="Jobs run in the worker; this list polls while anything is running"
        className="col-span-12 xl:col-span-8"
        bodyClassName="p-0"
        actions={
          <Link href="/backtesting/optimize" className="inline-flex items-center gap-1 text-[11px] text-accent-cyan"><SlidersHorizontal className="size-3" /> Optimise / walk-forward</Link>
        }
      >
        <JobsTable jobs={data} isPending={isPending} />
      </PanelCard>
    </div>
  );
}
