"use client";

import { useState } from "react";
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
  const cls = signed ? (v > 0 ? "text-up" : v < 0 ? "text-down" : "") : "";
  return <span className={cn("tabular", cls)}>{signed && v > 0 ? "+" : ""}{formatNumber(v, d)}</span>;
}

type Col = { key: keyof OptionChainRow; label: string; d: number; signed?: boolean; title?: string };

const BASE_COLS: Col[] = [
  { key: "oi", label: "OI", d: 0, title: "Open interest" },
  { key: "oi_change", label: "ΔOI", d: 0, signed: true, title: "OI change reported by the provider" },
  { key: "iv", label: "IV", d: 1, title: "Implied volatility, %" },
  { key: "delta", label: "Δ", d: 2, title: "Delta" },
  { key: "ltp", label: "LTP", d: 2, title: "Last traded price" },
];

/** Extra Greeks (Mark 1, 1.3), shown as the provider sent them; a missing value is "—". */
const GREEK_COLS: Col[] = [
  { key: "gamma", label: "Γ", d: 4, title: "Gamma" },
  { key: "theta", label: "Θ", d: 2, title: "Theta (per day)" },
  { key: "vega", label: "V", d: 2, title: "Vega" },
];

export function OptionChainTable({
  underlyingId,
  expiry,
  symbol,
  at,
}: {
  underlyingId: number | null;
  expiry?: string;
  symbol?: string;
  /** ISO datetime: show the snapshot stored at or before this moment instead of the latest. */
  at?: string;
}) {
  const { data, isPending, isError, error } = useOptionChain(underlyingId, expiry, at);
  const [greeks, setGreeks] = useState(false);
  // Greeks sit between IV/Δ and LTP so each side reads OI → Greeks → price towards the strike.
  const SIDE_COLS: Col[] = greeks ? [...BASE_COLS.slice(0, 4), ...GREEK_COLS, BASE_COLS[4]] : BASE_COLS;
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
      actions={
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-pressed={greeks}
            onClick={() => setGreeks((g) => !g)}
            className={cn(
              "hud-label rounded-[var(--r-pill)] border border-border px-2 py-0.5 text-[10px]",
              greeks ? "bg-accent-soft text-accent-text" : "text-text-3 hover:text-text-1",
            )}
          >
            Greeks
          </button>
          <DataStateBadge state={data ? data.freshness : "disconnected"} />
        </div>
      }
      bodyClassName="p-0"
    >
      {underlyingId == null ? (
        <EmptyState title="Select an underlying" className="m-3" />
      ) : isPending ? (
        <Skeleton className="m-3 h-64" />
      ) : notYet ? (
        <EmptyState
          title={at ? "No snapshot stored before that time" : "No snapshot yet"}
          description="The collector writes an option-chain snapshot every few minutes while the feed runs."
          className="m-3"
        />
      ) : isError ? (
        <EmptyState title="Could not load option chain" className="m-3" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase tracking-wide text-text-3">
              <tr className="border-b border-border">
                {SIDE_COLS.map((c) => (
                  <th key={`ce-${c.key}`} title={c.title} className="px-2 py-1.5 text-right font-medium">{c.label}</th>
                ))}
                <th className="bg-raised px-3 py-1.5 text-center font-semibold text-text-2">Strike</th>
                {[...SIDE_COLS].reverse().map((c) => (
                  <th key={`pe-${c.key}`} title={c.title} className="px-2 py-1.5 text-right font-medium">{c.label}</th>
                ))}
              </tr>
              <tr className="border-b border-border text-[10px]">
                <th colSpan={SIDE_COLS.length} className="py-0.5 text-center text-accent-text">CALLS</th>
                <th />
                <th colSpan={SIDE_COLS.length} className="py-0.5 text-center text-amber">PUTS</th>
              </tr>
            </thead>
            <tbody>
              {strikes.map((s) => {
                const { ce, pe } = byStrike.get(s)!;
                const isAtm = s === atm;
                return (
                  <tr key={s} className={cn("border-b border-border/60", isAtm && "bg-accent-soft")}>
                    {SIDE_COLS.map((c) => (
                      <td key={`ce-${c.key}`} className={cn("px-2 py-1 text-right", spot != null && s < spot && "bg-raised/40")}>
                        <N v={num(ce?.[c.key] as string | number | null | undefined)} d={c.d} signed={c.signed} />
                      </td>
                    ))}
                    <td className={cn("bg-raised px-3 py-1 text-center font-semibold tabular", isAtm ? "text-accent" : "text-text-1")}>
                      {formatNumber(s, 0)}
                    </td>
                    {[...SIDE_COLS].reverse().map((c) => (
                      <td key={`pe-${c.key}`} className={cn("px-2 py-1 text-right", spot != null && s > spot && "bg-raised/40")}>
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
