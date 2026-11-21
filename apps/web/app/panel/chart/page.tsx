"use client";

import { Suspense } from "react";
import { CandleChart, candleDataState } from "@/components/market/CandleChart";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { useInstrumentBySymbol, usePanelParams } from "@/components/panels/usePanel";
import type { Timeframe } from "@/lib/api/generated";
import { useCandles } from "@/lib/api/queries";
import { fullPageUrl } from "@/lib/panels";
import { useLiveQuote, useMarketSubscription } from "@/lib/ws/useMarket";

function ChartPanel() {
  const { values, errors } = usePanelParams("chart");
  const symbol = values.symbol;
  const tf = (values.tf ?? "5m") as Timeframe;
  const inst = useInstrumentBySymbol(errors.length ? undefined : symbol);
  const id = inst.data?.instrument_id ?? null;
  useMarketSubscription(id != null ? [id] : []);
  // Same queries as the chart itself (deduplicated), so header and chart agree on the state.
  const candles = useCandles(id, tf, 500);
  const { freshness } = useLiveQuote(id);

  const frame = (children: React.ReactNode, extra: { state?: Parameters<typeof PanelFrame>[0]["state"]; source?: string } = {}) => (
    <PanelFrame
      panel="chart"
      subtitle={symbol ? `${symbol} · ${tf}` : undefined}
      fullHref={id != null ? `/market?instrument=${id}` : fullPageUrl("chart")}
      bodyClassName="flex flex-col"
      {...extra}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="chart" errors={errors} />);
  if (inst.isPending) return frame(<PanelMessage title={`Resolving ${symbol}…`} />);
  if (inst.isError) return frame(<PanelMessage tone="error" title="Cannot reach the API" description="The instrument could not be looked up; nothing is shown in its place." />, { state: "disconnected" });
  if (!inst.data)
    return frame(
      <PanelMessage tone="error" title={`symbol: ${symbol} not found`} description="No NSE instrument with this symbol in the instrument master. Check the symbol, or sync the instrument master." />,
    );

  return frame(
    <CandleChart instrumentId={id} symbol={symbol} timeframe={tf} height="fill" bare className="min-h-0 flex-1" />,
    { state: candles.isPending ? undefined : candleDataState(candles.data, freshness), source: candles.data?.source },
  );
}

export default function ChartPanelPage() {
  return (
    <Suspense>
      <ChartPanel />
    </Suspense>
  );
}
