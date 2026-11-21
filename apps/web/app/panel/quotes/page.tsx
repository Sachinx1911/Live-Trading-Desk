"use client";

import { useQueries } from "@tanstack/react-query";
import { Suspense } from "react";
import { IndexCard } from "@/components/dashboard/IndexCard";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { api } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { fullPageUrl } from "@/lib/panels";
import { useRealtimeStore } from "@/lib/ws/store";
import { useMarketSubscription } from "@/lib/ws/useMarket";

function QuotesPanel() {
  const { values, errors } = usePanelParams("quotes");
  const symbols = errors.length ? [] : (values.symbols?.split(",") ?? []);
  const feed = useRealtimeStore((s) => s.providerFreshness);
  const resolved = useQueries({
    queries: symbols.map((sym) => ({
      queryKey: ["instruments", "by-symbol", sym],
      queryFn: async () => {
        const hits = await api<Instrument[]>(`/instruments?q=${encodeURIComponent(sym)}&exchange=NSE&limit=20`);
        return hits.find((i) => i.symbol === sym && i.segment === "index") ?? hits.find((i) => i.symbol === sym) ?? null;
      },
      staleTime: 5 * 60_000,
    })),
  });
  const ids = resolved.flatMap((r) => (r.data ? [r.data.instrument_id] : []));
  useMarketSubscription(ids);

  const frame = (children: React.ReactNode) => (
    <PanelFrame panel="quotes" subtitle={symbols.join(" · ") || undefined} state={errors.length ? undefined : feed} stateDetail="feed" fullHref={fullPageUrl("quotes")}>
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="quotes" errors={errors} />);
  if (resolved.some((r) => r.isError)) return frame(<PanelMessage tone="error" title="Cannot reach the API" description="Instruments could not be looked up; no prices are shown." />);

  return frame(
    <div className="grid min-h-full auto-rows-fr grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-2 p-2">
      {symbols.map((sym, i) => {
        const r = resolved[i];
        if (r.isPending) return <div key={sym} className="hud-panel rounded-[var(--r-sm)] border border-border bg-pane p-3 text-[12px] text-text-3">Resolving {sym}…</div>;
        if (!r.data)
          return (
            <div key={sym} className="hud-panel flex flex-col justify-center rounded-[var(--r-sm)] border border-down/50 bg-pane p-3">
              <p className="hud-label text-down">{sym}</p>
              <p className="text-[12px] text-text-3">symbols: {sym} not found in the instrument master</p>
            </div>
          );
        return <IndexCard key={sym} symbol={r.data.symbol} name={`${r.data.exchange} · ${r.data.segment}`} instrumentId={r.data.instrument_id} />;
      })}
    </div>,
  );
}

export default function QuotesPanelPage() {
  return (
    <Suspense>
      <QuotesPanel />
    </Suspense>
  );
}
