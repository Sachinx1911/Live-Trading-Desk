"use client";

import { EmptyState, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { BreadthIndexMove } from "@/lib/api/generated";
import { useBreadthLatest } from "@/lib/api/breadth";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

function fmtDay(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}

function Move({ label, m }: { label: string; m: BreadthIndexMove | undefined }) {
  if (!m || m.close == null) {
    return (
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wide text-text-3">{label}</span>
        <span className="text-text-3">—</span>
      </div>
    );
  }
  const pct = m.change_pct;
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-text-3">{label}</span>
      <span className="tabular text-text-1">{formatNumber(m.close, 2)}</span>
      <span className={cn("tabular text-[11px]", pct == null || pct === 0 ? "text-text-3" : pct > 0 ? "text-up" : "text-down")}>
        {pct == null ? "—" : `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`}
      </span>
    </div>
  );
}

/**
 * NIFTY 50 breadth for the latest stored session: advances vs declines, share above EMA 200 /
 * EMA 50, 52-week highs and lows, index moves. Values come only from `market_breadth` (derived
 * from one provider's stored daily candles); the as-of date and provider are always shown.
 */
export function BreadthTile({ className }: { className?: string }) {
  const { data, isPending, isError } = useBreadthLatest();
  const total = data ? data.advances + data.declines + data.unchanged : 0;
  const w = (n: number) => (total ? `${(n / total) * 100}%` : "0%");

  return (
    <PanelCard
      title="Market breadth"
      subtitle={data ? `NIFTY 50 · EOD ${fmtDay(data.as_of_date)} · ${data.provider.toUpperCase()}` : "NIFTY 50 · end of day"}
      className={className}
    >
      {isPending ? (
        <Skeleton className="h-24" />
      ) : isError ? (
        <EmptyState title="Breadth service unavailable" description="The API did not answer; nothing is assumed." />
      ) : !data ? (
        <EmptyState title="Not computed yet" description="The worker computes breadth at 16:25 IST from stored daily candles." />
      ) : (
        <div className="flex flex-col gap-3 text-xs">
          <div>
            <div className="mb-1 flex justify-between tabular">
              <span className="text-up">{data.advances} advances</span>
              {data.unchanged > 0 && <span className="text-text-3">{data.unchanged} unchanged</span>}
              <span className="text-down">{data.declines} declines</span>
            </div>
            <div className="flex h-2 w-full overflow-hidden rounded-[var(--r-sm)] bg-raised" role="img" aria-label={`${data.advances} advances, ${data.declines} declines, ${data.unchanged} unchanged`}>
              <div className="bg-up" style={{ width: w(data.advances) }} />
              <div className="bg-text-3" style={{ width: w(data.unchanged) }} />
              <div className="bg-down" style={{ width: w(data.declines) }} />
            </div>
          </div>
          <div className="grid grid-cols-4 gap-2">
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-text-3">&gt; EMA 200</span>
              <span className="tabular text-[15px] text-text-1">{data.above_ema200_pct == null ? "—" : `${data.above_ema200_pct.toFixed(0)}%`}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-text-3">&gt; EMA 50</span>
              <span className="tabular text-[15px] text-text-1">{data.above_ema50_pct == null ? "—" : `${data.above_ema50_pct.toFixed(0)}%`}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-text-3">52w highs</span>
              <span className="tabular text-[15px] text-up">{data.new_52w_high}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] uppercase tracking-wide text-text-3">52w lows</span>
              <span className="tabular text-[15px] text-down">{data.new_52w_low}</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 border-t border-border pt-2">
            <Move label="NIFTY" m={data.index_moves.NIFTY} />
            <Move label="BANKNIFTY" m={data.index_moves.BANKNIFTY} />
            <Move label="INDIA VIX" m={data.index_moves.INDIAVIX} />
          </div>
          <p className="text-[11px] text-text-3">
            {data.universe_size} of 50 members had a bar that day · close basis, 252-session 52-week window
          </p>
        </div>
      )}
    </PanelCard>
  );
}
