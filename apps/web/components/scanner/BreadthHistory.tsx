"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { MarketBreadth } from "@/lib/api/generated";
import { useBreadthHistory, useRebuildBreadth } from "@/lib/api/breadth";
import { useMe } from "@/lib/api/queries";

const H = 120;

/**
 * Small history of NIFTY 50 breadth: bars = advances − declines per session (green above zero,
 * red below), line = % of members above EMA 200 (0–100 on the same height). Stored rows only.
 */
export function BreadthHistory({ className, bare = false }: { className?: string; bare?: boolean }) {
  const { data, isPending, isError } = useBreadthHistory("NIFTY50", 120);
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const rebuild = useRebuildBreadth();
  const [hover, setHover] = useState<MarketBreadth | null>(null);
  const rows = data?.rows ?? [];
  const n = rows.length;
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.advances - r.declines)));
  const bw = n ? 100 / n : 0;
  const mid = H / 2;
  const line = rows
    .map((r, i) => (r.above_ema200_pct == null ? null : `${(i + 0.5) * bw},${H - (r.above_ema200_pct / 100) * H}`))
    .filter(Boolean)
    .join(" ");
  const last = rows.at(-1);
  const shown = hover ?? last;

  const fromDate = (() => {
    const d = new Date();
    d.setDate(d.getDate() - 120);
    return d.toISOString().slice(0, 10);
  })();

  return (
    <PanelCard
      title="Breadth history"
      subtitle={data ? `NIFTY 50 · ${n} sessions · ${data.provider.toUpperCase()} daily candles` : "NIFTY 50"}
      className={className}
      bare={bare}
      actions={
        isOwner && (
          <Button size="xs" variant="ghost" disabled={rebuild.isPending} onClick={() => rebuild.mutate({ from_date: fromDate })} title="Recompute the last ~120 days in the worker">
            <RefreshCw className="size-3" /> rebuild
          </Button>
        )
      }
    >
      {rebuild.isSuccess && <p className="mb-2 text-[12px] text-text-2">Rebuild queued in the worker.</p>}
      {isPending ? (
        <Skeleton className="h-28" />
      ) : isError ? (
        <EmptyState title="Breadth service unavailable" />
      ) : n === 0 ? (
        <EmptyState title="No breadth stored yet" description="Computed daily at 16:25 IST; the first run back-fills 60 sessions." />
      ) : (
        <div className="flex flex-col gap-2">
          {shown && (
            <div className="flex flex-wrap gap-x-4 text-[12px] tabular text-text-2">
              <span className="text-text-1">{shown.as_of_date}</span>
              <span>
                A/D <span className="text-up">{shown.advances}</span>/<span className="text-down">{shown.declines}</span>
              </span>
              <span>&gt; EMA 200 {shown.above_ema200_pct == null ? "—" : `${shown.above_ema200_pct.toFixed(0)}%`}</span>
              <span>
                52w H/L {shown.new_52w_high}/{shown.new_52w_low}
              </span>
            </div>
          )}
          <svg viewBox={`0 0 100 ${H}`} preserveAspectRatio="none" className="h-32 w-full" onMouseLeave={() => setHover(null)} role="img" aria-label="Advances minus declines per session with share above EMA 200">
            <line x1={0} x2={100} y1={mid} y2={mid} className="stroke-border" strokeWidth={0.5} vectorEffect="non-scaling-stroke" />
            {rows.map((r, i) => {
              const v = r.advances - r.declines;
              const h = (Math.abs(v) / maxAbs) * (mid - 2);
              return (
                <g key={r.as_of_date} onMouseEnter={() => setHover(r)}>
                  <rect x={i * bw} y={0} width={bw} height={H} fill="transparent" />
                  <rect x={i * bw + bw * 0.15} width={bw * 0.7} y={v >= 0 ? mid - h : mid} height={Math.max(h, 0.5)} className={v >= 0 ? "fill-up" : "fill-down"} opacity={hover && hover !== r ? 0.5 : 0.85} />
                </g>
              );
            })}
            {line && <polyline points={line} fill="none" className="stroke-amber" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />}
          </svg>
          <div className="flex justify-between text-[11px] text-text-3">
            <span>{rows[0]?.as_of_date}</span>
            <span>
              <span className="text-up">▮</span>/<span className="text-down">▮</span> advances − declines · <span className="text-amber">—</span> % above EMA 200
            </span>
            <span>{last?.as_of_date}</span>
          </div>
        </div>
      )}
    </PanelCard>
  );
}
