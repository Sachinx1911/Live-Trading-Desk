"use client";

import { RefreshCw } from "lucide-react";
import { EmptyState, PanelCard } from "@/components/design";
import { DayTypeBadge, EventBadge, RegimeNumbers, StructureBadge, TrendBadge, VolBadge } from "@/components/market/RegimeBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/lib/api/queries";
import { useRecomputeRegime, useRegimeSummary } from "@/lib/api/regime";
import { formatAge, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Dashboard tile: one row per index with today's deterministic labels. Everything shown comes
 * from `/market/regime/summary`; when nothing has been computed the tile says so and offers the
 * owner a recompute, it never guesses a regime.
 */
export function RegimeTile({ className }: { className?: string }) {
  const { data, isPending, isError } = useRegimeSummary();
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const recompute = useRecomputeRegime();

  const latest = data?.map((r) => r.today?.computed_at).filter(Boolean).sort().at(-1);
  const actions = (
    <div className="flex items-center gap-2">
      {latest && <span className="text-[11px] text-text-3">computed {formatAge(latest)} ago</span>}
      {isOwner && (
        <Button size="xs" variant="ghost" onClick={() => recompute.mutate()} disabled={recompute.isPending} title="Queue the regime job in the worker">
          <RefreshCw className={cn("size-3", recompute.isPending && "animate-spin")} /> recompute
        </Button>
      )}
    </div>
  );

  return (
    <PanelCard title="Market regime" subtitle="Deterministic: EMA/ADX, VIX percentile, structure, day type" actions={actions} className={className} bodyClassName="p-0">
      {isPending ? (
        <Skeleton className="m-3 h-16" />
      ) : isError ? (
        <EmptyState title="Regime service unavailable" description="The API did not answer; nothing is assumed." className="m-3" />
      ) : !data || data.length === 0 || data.every((r) => !r.today) ? (
        <EmptyState
          title="Not computed yet"
          description={recompute.isSuccess ? "Recompute queued; the worker writes today's regime shortly." : "The regime job runs at 09:05 IST and after close. Owners can queue it now."}
          className="m-3"
        />
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-text-3">
            <tr className="border-b border-border">
              <th className="px-3 py-1.5 text-left font-medium">Index</th>
              <th className="px-3 py-1.5 text-left font-medium">Trend</th>
              <th className="px-3 py-1.5 text-left font-medium">Volatility</th>
              <th className="px-3 py-1.5 text-left font-medium">Structure</th>
              <th className="px-3 py-1.5 text-left font-medium">Day type</th>
              <th className="px-3 py-1.5 text-left font-medium">Event</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => {
              const d = r.today;
              const tip = d ? <RegimeNumbers d={d} intraday={r.intraday} /> : null;
              return (
                <tr key={r.instrument_id} className="border-b border-border/60">
                  <td className="px-3 py-2 font-semibold text-text-1">
                    {r.symbol}
                    {d && <span className="ml-2 font-normal text-text-3">{formatDateTime(d.date).slice(0, 11)}</span>}
                  </td>
                  {d ? (
                    <>
                      <td className="px-3 py-2"><TrendBadge d={d} tip={tip} /></td>
                      <td className="px-3 py-2"><VolBadge v={d.volatility} tip={tip} /></td>
                      <td className="px-3 py-2"><StructureBadge s={d.structure} tip={tip} /></td>
                      <td className="px-3 py-2">{r.intraday ? <DayTypeBadge t={r.intraday.day_type} tip={tip} /> : <span className="text-text-3" title="Day type is classified after 09:45 IST">—</span>}</td>
                      <td className="px-3 py-2">{d.event_day ? <EventBadge events={d.events} /> : <span className="text-text-3">—</span>}</td>
                    </>
                  ) : (
                    <td colSpan={5} className="px-3 py-2 text-text-3">not computed for this index</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </PanelCard>
  );
}
