"use client";

import { useEffect, useState } from "react";
import { CandleChart } from "@/components/market/CandleChart";
import { api } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { useMarketSubscription } from "@/lib/ws/useMarket";
import { IndexCard } from "./IndexCard";

const SYMBOLS = ["NIFTY", "BANKNIFTY"] as const;

/** Resolves the index instruments once and drives the tiles + chart from the live store. */
export function MarketStrip() {
  const [ids, setIds] = useState<Record<string, number>>({});
  useEffect(() => {
    let alive = true;
    void (async () => {
      const out: Record<string, number> = {};
      for (const sym of SYMBOLS) {
        try {
          const hits = await api<Instrument[]>(`/instruments?q=${sym}&exchange=NSE&limit=20`);
          const hit = hits.find((i) => i.symbol === sym && i.segment === "index") ?? hits.find((i) => i.symbol === sym);
          if (hit) out[sym] = hit.instrument_id;
        } catch {
          /* tiles stay Disconnected */
        }
      }
      if (alive) setIds(out);
    })();
    return () => {
      alive = false;
    };
  }, []);
  useMarketSubscription(Object.values(ids));
  return (
    <>
      <div className="col-span-12 grid grid-cols-3 gap-3">
        <IndexCard symbol="NIFTY 50" name="NSE · Index" instrumentId={ids.NIFTY ?? null} />
        <IndexCard symbol="BANKNIFTY" name="NSE · Index" instrumentId={ids.BANKNIFTY ?? null} />
        <IndexCard symbol="SENSEX" name="BSE · Index" reason="BSE adapter ships in Phase 9" />
      </div>
      <CandleChart instrumentId={ids.NIFTY ?? null} symbol="NIFTY 50" timeframe="5m" className="col-span-12 xl:col-span-8" height={300} />
    </>
  );
}
