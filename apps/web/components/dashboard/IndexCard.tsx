"use client";

import { DataStateBadge, Dash, Pct } from "@/components/design";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { num, useLiveQuote } from "@/lib/ws/useMarket";

/**
 * Index tile, HUD style: monospaced symbol label, one hero price (36px, tabular) with the
 * coloured change beside it (design references: "one big number with a label").
 * Renders a price only from a real quote in the realtime store; otherwise an em-dash and an
 * explicit Disconnected badge with the reason. Demo quotes keep the demo stripes instead of
 * the corner frame (both are background images; the demo marking must win).
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
    <div
      className={cn(
        "hud-panel hud-glow flex flex-col gap-2 rounded-[var(--r-sm)] border border-border bg-pane p-3",
        quote?.is_demo ? "demo-stripes" : "hud-frame",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="hud-label text-[12px] text-accent-text">{symbol}</p>
          <p className="text-[12px] text-text-3">{name}</p>
        </div>
        <DataStateBadge state={freshness} />
      </div>
      <div className="flex items-baseline gap-3">
        {ltp == null ? (
          <Dash className="text-[36px] leading-10 font-semibold" />
        ) : (
          <span className={cn("tabular font-mono text-[36px] leading-10 font-semibold text-text-1", freshness === "stale" && "text-text-2")}>
            {formatNumber(ltp, 2)}
          </span>
        )}
        <Pct value={chg} className="text-[16px] font-semibold" />
      </div>
      <p className="text-[12px] text-text-3">{quote ? `${quote.provider_id}${quote.is_demo ? " · demo" : ""}` : reason}</p>
    </div>
  );
}
