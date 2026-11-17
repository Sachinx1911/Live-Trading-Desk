"use client";

import { DataStateBadge, Dash } from "@/components/design";
import type { Freshness } from "@/lib/api/generated";

/**
 * Index tile. In Phase 1 there is no quote source, so the card renders an em-dash and an
 * explicit Disconnected badge. A price is only ever rendered from a real API quote.
 */
export function IndexCard({
  symbol,
  name,
  state = "disconnected",
  reason = "No market data provider connected",
}: {
  symbol: string;
  name: string;
  state?: Freshness;
  reason?: string;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-panel p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-text-primary">{symbol}</p>
          <p className="text-[11px] text-text-muted">{name}</p>
        </div>
        <DataStateBadge state={state} />
      </div>
      <div className="flex items-baseline gap-3">
        <Dash className="text-2xl font-semibold" />
        <Dash className="text-xs" />
      </div>
      <p className="text-[11px] text-text-muted">{reason}</p>
    </div>
  );
}
