"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import { DataStateBadge, DemoBanner, EmptyState, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { Candle, Timeframe } from "@/lib/api/generated";
import { useCandles } from "@/lib/api/queries";
import { marketSocket } from "@/lib/ws/market";
import { num, useLiveQuote } from "@/lib/ws/useMarket";
import { cn } from "@/lib/utils";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "1d"];
const IST_OFFSET_S = 5.5 * 3600;
const TF_SECONDS: Record<string, number> = { "1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400 };

/** Chart times are shifted to IST so the axis reads like the exchange clock. */
function toTime(iso: string): UTCTimestamp {
  return (Math.floor(new Date(iso).getTime() / 1000) + IST_OFFSET_S) as UTCTimestamp;
}

function toBar(c: Candle): CandlestickData<Time> {
  return { time: toTime(c.ts), open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close) };
}

function toVol(c: Candle): HistogramData<Time> {
  const up = Number(c.close) >= Number(c.open);
  return { time: toTime(c.ts), value: c.volume, color: up ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)" };
}

export function CandleChart({
  instrumentId,
  symbol,
  timeframe,
  onTimeframe,
  className,
  height = 360,
}: {
  instrumentId: number | null;
  symbol?: string;
  timeframe: Timeframe;
  onTimeframe?: (tf: Timeframe) => void;
  className?: string;
  height?: number;
}) {
  const { data, isPending, isError } = useCandles(instrumentId, timeframe, 500);
  const { quote, freshness } = useLiveQuote(instrumentId);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const lastBarRef = useRef<CandlestickData<Time> | null>(null);

  const candles = useMemo(() => data?.candles ?? [], [data]);

  // Create chart once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8b95ad", fontSize: 11 },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      borderVisible: false,
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chartRef.current = chart;
    candleRef.current = candle;
    volRef.current = vol;
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
    };
  }, [height]);

  // Load history.
  useEffect(() => {
    const c = candleRef.current;
    const v = volRef.current;
    if (!c || !v) return;
    const bars = candles.map(toBar);
    c.setData(bars);
    v.setData(candles.map(toVol));
    lastBarRef.current = bars.length ? bars[bars.length - 1] : null;
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // Append closed bars from the socket.
  useEffect(() => {
    if (instrumentId == null) return;
    return marketSocket.onCandle((cd) => {
      if (cd.instrument_id !== instrumentId || cd.timeframe !== timeframe) return;
      const bar = toBar(cd);
      const last = lastBarRef.current;
      if (last && bar.time < last.time) return;
      candleRef.current?.update(bar);
      volRef.current?.update(toVol(cd));
      lastBarRef.current = bar;
    });
  }, [instrumentId, timeframe]);

  // Update the forming bar from ticks.
  useEffect(() => {
    if (!quote || quote.instrument_id !== instrumentId) return;
    const ltp = num(quote.ltp);
    const step = TF_SECONDS[timeframe];
    if (ltp == null || !step) return;
    const t = (Math.floor((Math.floor(new Date(quote.ts).getTime() / 1000) + IST_OFFSET_S) / step) * step) as UTCTimestamp;
    const last = lastBarRef.current;
    let bar: CandlestickData<Time>;
    if (last && last.time === t) bar = { ...last, high: Math.max(last.high, ltp), low: Math.min(last.low, ltp), close: ltp };
    else if (!last || t > (last.time as number)) bar = { time: t, open: ltp, high: ltp, low: ltp, close: ltp };
    else return;
    candleRef.current?.update(bar);
    lastBarRef.current = bar;
  }, [quote, instrumentId, timeframe]);

  const badgeState = data ? (data.is_demo ? "demo" : candles.length ? (freshness === "disconnected" ? "historical" : freshness) : "disconnected") : "disconnected";

  return (
    <PanelCard
      title={symbol ? `${symbol} · ${timeframe}` : "Chart"}
      subtitle={data ? `source ${data.source}` : undefined}
      banner={data?.is_demo ? <DemoBanner /> : undefined}
      className={className}
      bodyClassName="p-0"
      actions={
        <div className="flex items-center gap-2">
          {onTimeframe && (
            <div className="flex rounded-sm border border-border-subtle">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onTimeframe(tf)}
                  className={cn(
                    "px-2 py-0.5 text-[11px] font-medium",
                    tf === timeframe ? "bg-panel-raised text-cyan-accent" : "text-text-muted hover:text-text-secondary",
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          )}
          <DataStateBadge state={badgeState} />
        </div>
      }
    >
      {instrumentId == null ? (
        <EmptyState title="Select an instrument" className="m-3" />
      ) : isPending ? (
        <Skeleton className="m-3 h-72" />
      ) : isError ? (
        <EmptyState title="Could not load candles" description="The API returned an error; nothing is shown in its place." className="m-3" />
      ) : candles.length === 0 ? (
        <EmptyState title="No data yet" description="No candles stored for this instrument and timeframe. The collector builds 1-minute bars while the feed runs." className="m-3" />
      ) : null}
      <div ref={containerRef} className={cn("w-full", (instrumentId == null || isPending || candles.length === 0) && "hidden")} />
    </PanelCard>
  );
}
