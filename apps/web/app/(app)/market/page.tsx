"use client";

import { useState } from "react";
import { CandleChart } from "@/components/market/CandleChart";
import { QuoteDetails } from "@/components/market/QuoteDetails";
import { Watchlist, type WatchItem } from "@/components/market/Watchlist";
import type { Timeframe } from "@/lib/api/generated";

export default function MarketPage() {
  const [selected, setSelected] = useState<WatchItem | null>(null);
  const [tf, setTf] = useState<Timeframe>("5m");
  return (
    <div className="grid grid-cols-12 gap-3">
      <Watchlist selectedId={selected?.instrument_id ?? null} onSelect={setSelected} className="col-span-12 xl:col-span-3" />
      <div className="col-span-12 flex flex-col gap-3 xl:col-span-9">
        <CandleChart instrumentId={selected?.instrument_id ?? null} symbol={selected?.label} timeframe={tf} onTimeframe={setTf} height={420} />
        <QuoteDetails instrumentId={selected?.instrument_id ?? null} symbol={selected?.label} />
      </div>
    </div>
  );
}
