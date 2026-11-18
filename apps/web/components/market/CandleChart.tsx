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
import { chartPalette, onThemeChange, withAlpha } from "@/lib/theme";
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

function toVol(c: Candle, pal: ReturnType<typeof chartPalette>): HistogramData<Time> {
  const up = Number(c.close) >= Number(c.open);
  // 45% alpha of the candle colour (reference §6)
  return { time: toTime(c.ts), value: c.volume, color: withAlpha(up ? pal.up : pal.down, 0.45) };
}

/** Theme-dependent chart options; applied at creation and on every theme change. */
function themeOptions(pal: ReturnType<typeof chartPalette>) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: pal.bg },
      textColor: pal.text,
      fontSize: 12,
      fontFamily: "-apple-system, system-ui, Segoe UI, Roboto, sans-serif",
    },
    grid: { vertLines: { visible: false }, horzLines: { color: pal.grid } },
    rightPriceScale: { borderColor: pal.border },
    timeScale: { borderColor: pal.border, timeVisible: true, secondsVisible: false },
    crosshair: {
      mode: 0,
      vertLine: { color: pal.crosshair, labelBackgroundColor: pal.crosshairLabel },
      horzLine: { color: pal.crosshair, labelBackgroundColor: pal.crosshairLabel },
    },
  } as const;
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
  const palRef = useRef(chartPalette());
  const volDataRef = useRef<Candle[]>([]);

  const candles = useMemo(() => data?.candles ?? [], [data]);
  // Legend: last stored bar, with the live last price folded into the close (render-safe state).
  const legend = useMemo(() => {
    const last = candles[candles.length - 1];
    if (!last) return null;
    const bar = { open: Number(last.open), high: Number(last.high), low: Number(last.low), close: Number(last.close) };
    const ltp = quote && quote.instrument_id === instrumentId ? num(quote.ltp) : null;
    if (ltp != null) {
      bar.close = ltp;
      bar.high = Math.max(bar.high, ltp);
      bar.low = Math.min(bar.low, ltp);
    }
    return bar;
  }, [candles, quote, instrumentId]);

  // Create chart once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const pal = chartPalette();
    palRef.current = pal;
    const chart = createChart(el, { height, ...themeOptions(pal) });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: pal.up,
      downColor: pal.down,
      wickUpColor: pal.up,
      wickDownColor: pal.down,
      borderVisible: false,
      priceLineColor: pal.priceLine,
      priceLineWidth: 1,
      lastValueVisible: true,
    });
    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chartRef.current = chart;
    candleRef.current = candle;
    volRef.current = vol;
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    ro.observe(el);
    // Re-skin on theme change: chart options, candle colours and the volume bars' colours.
    const offTheme = onThemeChange(() => {
      const next = chartPalette();
      palRef.current = next;
      chart.applyOptions(themeOptions(next));
      candle.applyOptions({ upColor: next.up, downColor: next.down, wickUpColor: next.up, wickDownColor: next.down, priceLineColor: next.priceLine });
      vol.setData(volDataRef.current.map((c) => toVol(c, next)));
    });
    return () => {
      offTheme();
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
    volDataRef.current = candles;
    v.setData(candles.map((cd) => toVol(cd, palRef.current)));
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
      volRef.current?.update(toVol(cd, palRef.current));
      volDataRef.current = [...volDataRef.current.filter((x) => x.ts !== cd.ts), cd];
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
            <div className="flex items-center gap-0.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onTimeframe(tf)}
                  className={cn(
                    "h-6 rounded-[var(--r-pill)] px-2.5 text-[12px] transition-colors",
                    tf === timeframe ? "bg-raised text-text-1" : "text-text-3 hover:bg-hover hover:text-text-2",
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
      <div className={cn("relative", (instrumentId == null || isPending || candles.length === 0) && "hidden")}>
        {symbol && (
          <div className="pointer-events-none absolute top-2 left-3 z-10 flex items-baseline gap-2 opacity-60">
            <span className="text-[16px] text-text-1">{symbol}</span>
            <span className="text-[13px] text-text-2">{timeframe}</span>
            {legend && (
              <span className="tabular text-[13px] text-text-2">
                O {legend.open.toFixed(2)} H {legend.high.toFixed(2)} L {legend.low.toFixed(2)} C{" "}
                <span className={legend.close >= legend.open ? "text-up" : "text-down"}>{legend.close.toFixed(2)}</span>
              </span>
            )}
          </div>
        )}
        <div ref={containerRef} className="w-full" />
      </div>
    </PanelCard>
  );
}
