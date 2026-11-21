"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { OpenAsPanel } from "@/components/panels/OpenAsPanel";
import { CandleChart } from "@/components/market/CandleChart";
import { InstrumentNews } from "@/components/market/InstrumentNews";
import { instrumentLabel } from "@/components/market/InstrumentSearch";
import { QuoteDetails } from "@/components/market/QuoteDetails";
import { RegimeStrip } from "@/components/market/RegimeStrip";
import { Watchlist, type WatchItem } from "@/components/market/Watchlist";
import { api } from "@/lib/api/client";
import type { Instrument, Timeframe } from "@/lib/api/generated";

function MarketContent() {
  const params = useSearchParams();
  const wanted = params.get("instrument");
  const [selected, setSelected] = useState<WatchItem | null>(null);
  const [tf, setTf] = useState<Timeframe>("5m");

  // Top-bar symbol search lands here with ?instrument=<id>: select it without adding to the list.
  useEffect(() => {
    if (!wanted) return;
    const id = Number(wanted);
    if (!Number.isFinite(id) || selected?.instrument_id === id) return;
    let alive = true;
    void api<Instrument>(`/instruments/${id}`)
      .then((i) => {
        if (alive) setSelected({ instrument_id: i.instrument_id, symbol: i.symbol, segment: i.segment, name: i.name, label: instrumentLabel(i) });
      })
      .catch(() => {
        /* unknown id: the page keeps its current selection */
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted]);

  return (
    <div className="grid grid-cols-12 gap-px bg-border">
      <Watchlist selectedId={selected?.instrument_id ?? null} onSelect={setSelected} className="col-span-12 border-0 xl:col-span-3" />
      <div className="col-span-12 flex flex-col gap-px bg-border xl:col-span-9">
        <RegimeStrip instrumentId={selected?.instrument_id ?? null} className="border-b-0" />
        <CandleChart
          instrumentId={selected?.instrument_id ?? null}
          symbol={selected?.label}
          timeframe={tf}
          onTimeframe={setTf}
          height={440}
          className="border-0"
          headerExtra={selected ? <OpenAsPanel panel="chart" params={{ symbol: selected.symbol, tf }} /> : undefined}
        />
        <QuoteDetails instrumentId={selected?.instrument_id ?? null} symbol={selected?.label} />
        <InstrumentNews symbol={selected?.symbol ?? null} segment={selected?.segment ?? null} className="border-0" />
      </div>
    </div>
  );
}

export default function MarketPage() {
  return (
    <Suspense>
      <MarketContent />
    </Suspense>
  );
}
