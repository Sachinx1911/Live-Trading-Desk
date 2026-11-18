"use client";

import { DataStateBadge, Dash, PanelCard } from "@/components/design";
import { formatNumber, formatTime } from "@/lib/format";
import { num, useLiveQuote } from "@/lib/ws/useMarket";

function Cell({ label, value, digits = 2 }: { label: string; value: number | null; digits?: number }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-text-3">{label}</span>
      {value == null ? <Dash className="text-sm" /> : <span className="tabular text-sm text-text-1">{formatNumber(value, digits)}</span>}
    </div>
  );
}

export function QuoteDetails({ instrumentId, symbol }: { instrumentId: number | null; symbol?: string }) {
  const { quote, freshness } = useLiveQuote(instrumentId);
  return (
    <PanelCard
      title={symbol ? `${symbol} · quote` : "Quote"}
      subtitle={quote ? `${quote.provider_id} · ${formatTime(quote.ts)}` : "No quote received"}
      actions={<DataStateBadge state={freshness} />}
    >
      <div className="grid grid-cols-4 gap-3 md:grid-cols-8">
        <Cell label="LTP" value={num(quote?.ltp)} />
        <Cell label="Bid" value={num(quote?.bid)} />
        <Cell label="Bid qty" value={quote?.bid_qty ?? null} digits={0} />
        <Cell label="Ask" value={num(quote?.ask)} />
        <Cell label="Ask qty" value={quote?.ask_qty ?? null} digits={0} />
        <Cell label="Volume" value={quote?.volume ?? null} digits={0} />
        <Cell label="OI" value={quote?.oi ?? null} digits={0} />
        <Cell label="Prev close" value={num(quote?.prev_close)} />
        <Cell label="Open" value={num(quote?.open)} />
        <Cell label="High" value={num(quote?.high)} />
        <Cell label="Low" value={num(quote?.low)} />
      </div>
    </PanelCard>
  );
}
