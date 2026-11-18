"use client";

import { RegimeBadges, STRUCT_LABEL, TREND_LABEL, VOL_LABEL, trendCellClass } from "@/components/market/RegimeBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRegime } from "@/lib/api/regime";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * One-line regime strip above the chart: today's labels plus 30 one-day cells coloured by
 * trend (intensity = strength). Cells only exist for days the worker actually classified.
 */
export function RegimeStrip({ instrumentId, days = 30, className }: { instrumentId: number | null; days?: number; className?: string }) {
  const { data, isPending, isError } = useRegime(instrumentId, days);

  if (instrumentId == null) return null;
  return (
    <div className={cn("flex min-h-9 flex-wrap items-center justify-between gap-2 border-b border-border bg-pane px-3 py-1.5", className)}>
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-text-3">Regime</span>
        {isPending ? (
          <Skeleton className="h-5 w-48" />
        ) : isError || !data ? (
          <span className="text-[12px] text-text-3">unavailable</span>
        ) : data.today ? (
          <RegimeBadges d={data.today} intraday={data.intraday} />
        ) : (
          <span className="text-[12px] text-text-3">not computed yet</span>
        )}
      </div>
      {data && data.history.length > 0 && (
        <div className="flex items-center gap-1" aria-label={`${data.history.length}-day regime history`}>
          <span className="mr-1 text-[10px] text-text-3">{data.history.length}d</span>
          <div className="flex items-center gap-px">
            {data.history.map((d) => (
              <Tooltip key={d.date}>
                <TooltipTrigger render={<span className={cn("block h-3 w-1.5 rounded-[1px]", trendCellClass(d))} />} />
                <TooltipContent>
                  <div className="text-[11px]">
                    <div className="font-medium">{formatDateTime(d.date).slice(0, 11)}</div>
                    <div className="text-text-2">
                      {TREND_LABEL(d.trend)} · {d.strength} · {VOL_LABEL(d.volatility)} · {STRUCT_LABEL(d.structure)}
                      {d.event_day ? " · event" : ""}
                    </div>
                  </div>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
