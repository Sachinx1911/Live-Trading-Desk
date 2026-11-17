"use client";

import { DataStateBadge, Dash, Pct } from "@/components/design";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { num, useLiveQuote } from "@/lib/ws/useMarket";

/**
 * Index tile. Renders a price only from a real quote in the realtime store; otherwise an
 * em-dash and an explicit Disconnected badge with the reason.
 */
export function IndexCard({
  symbol,
  name,
  instrumentId = null,
  reason = "No market data provider connected",
}: {
  symbol: string;
  name: string;
  instrumentId?: number | null;
  reason?: string;
}) {
  const { quote, freshness } = useLiveQuote(instrumentId);
  const ltp = num(quote?.ltp);
  const prev = num(quote?.prev_close);
  const chg = ltp != null && prev ? ((ltp - prev) / prev) * 100 : null;
  return (
    <div className={cn("flex flex-col gap-2 rounded-md border border-border-subtle bg-panel p-3", quote?.is_demo && "demo-stripes")}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-text-primary">{symbol}</p>
          <p className="text-[11px] text-text-muted">{name}</p>
        </div>
        <DataStateBadge state={freshness} />
      </div>
      <div className="flex items-baseline gap-3">
        {ltp == null ? <Dash className="text-2xl font-semibold" /> : <span className="tabular text-2xl font-semibold text-text-primary">{formatNumber(ltp, 2)}</span>}
        <Pct value={chg} className="text-xs" />
      </div>
      <p className="text-[11px] text-text-muted">{quote ? `${quote.provider_id}${quote.is_demo ? " · demo" : ""}` : reason}</p>
    </div>
  );
}
