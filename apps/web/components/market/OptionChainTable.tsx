"use client";

import { DataStateBadge, Dash, DemoBanner, EmptyState, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/lib/api/client";
import type { OptionChainRow } from "@/lib/api/generated";
import { useOptionChain } from "@/lib/api/queries";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { num } from "@/lib/ws/useMarket";

function N({ v, d = 2, signed = false }: { v: number | null; d?: number; signed?: boolean }) {
  if (v == null) return <Dash />;
  const cls = signed ? (v > 0 ? "text-pnl-positive" : v < 0 ? "text-pnl-negative" : "") : "";
  return <span className={cn("tabular", cls)}>{signed && v > 0 ? "+" : ""}{formatNumber(v, d)}</span>;
}

const SIDE_COLS: { key: keyof OptionChainRow; label: string; d: number; signed?: boolean }[] = [
  { key: "oi", label: "OI", d: 0 },
  { key: "oi_change", label: "ΔOI", d: 0, signed: true },
  { key: "iv", label: "IV", d: 1 },
  { key: "delta", label: "Δ", d: 2 },
  { key: "ltp", label: "LTP", d: 2 },
];

export function OptionChainTable({ underlyingId, expiry, symbol }: { underlyingId: number | null; expiry?: string; symbol?: string }) {
  const { data, isPending, isError, error } = useOptionChain(underlyingId, expiry);
  const notYet = isError && error instanceof ApiRequestError && error.status === 404;

  const byStrike = new Map<number, { ce?: OptionChainRow; pe?: OptionChainRow }>();
  for (const r of data?.rows ?? []) {
    const k = Number(r.strike);
    const e = byStrike.get(k) ?? {};
    if (r.option_type === "CE") e.ce = r;
    else e.pe = r;
    byStrike.set(k, e);
  }
  const strikes = [...byStrike.keys()].sort((a, b) => a - b);
  const spot = num(data?.underlying_price);
  const atm = spot != null && strikes.length ? strikes.reduce((best, s) => (Math.abs(s - spot) < Math.abs(best - spot) ? s : best), strikes[0]) : null;

  return (
    <PanelCard
      title={symbol ? `${symbol} option chain` : "Option chain"}
      subtitle={data ? `snapshot ${formatDateTime(data.ts)} · source ${data.source} · spot ${spot != null ? formatNumber(spot, 2) : "—"}` : undefined}
      banner={data?.source === "fake" ? <DemoBanner /> : undefined}
      actions={<DataStateBadge state={data ? data.freshness : "disconnected"} />}
      bodyClassName="p-0"
    >
      {underlyingId == null ? (
        <EmptyState title="Select an underlying" className="m-3" />
      ) : isPending ? (
        <Skeleton className="m-3 h-64" />
      ) : notYet ? (
        <EmptyState title="No snapshot yet" description="The collector writes an option-chain snapshot every 5 minutes while the feed runs." className="m-3" />
      ) : isError ? (
        <EmptyState title="Could not load option chain" className="m-3" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-text-muted">
              <tr className="border-b border-border-subtle">
                {SIDE_COLS.map((c) => (
                  <th key={`ce-${c.key}`} className="px-2 py-1.5 text-right font-medium">{c.label}</th>
                ))}
                <th className="bg-panel-raised px-3 py-1.5 text-center font-semibold text-text-secondary">Strike</th>
                {[...SIDE_COLS].reverse().map((c) => (
                  <th key={`pe-${c.key}`} className="px-2 py-1.5 text-right font-medium">{c.label}</th>
                ))}
              </tr>
              <tr className="border-b border-border-subtle text-[10px]">
                <th colSpan={SIDE_COLS.length} className="py-0.5 text-center text-pnl-positive">CALLS</th>
                <th />
                <th colSpan={SIDE_COLS.length} className="py-0.5 text-center text-pnl-negative">PUTS</th>
              </tr>
            </thead>
            <tbody>
              {strikes.map((s) => {
                const { ce, pe } = byStrike.get(s)!;
                const isAtm = s === atm;
                return (
                  <tr key={s} className={cn("border-b border-border-subtle/60", isAtm && "bg-cyan-dim/30")}>
                    {SIDE_COLS.map((c) => (
                      <td key={`ce-${c.key}`} className={cn("px-2 py-1 text-right", spot != null && s < spot && "bg-panel-raised/40")}>
                        <N v={num(ce?.[c.key] as string | number | null | undefined)} d={c.d} signed={c.signed} />
                      </td>
                    ))}
                    <td className={cn("bg-panel-raised px-3 py-1 text-center font-semibold tabular", isAtm ? "text-cyan-accent" : "text-text-primary")}>
                      {formatNumber(s, 0)}
                    </td>
                    {[...SIDE_COLS].reverse().map((c) => (
                      <td key={`pe-${c.key}`} className={cn("px-2 py-1 text-right", spot != null && s > spot && "bg-panel-raised/40")}>
                        <N v={num(pe?.[c.key] as string | number | null | undefined)} d={c.d} signed={c.signed} />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PanelCard>
  );
}
