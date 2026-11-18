"use client";

/**
 * Chart for one replay session. Two candlestick series on the same price scale:
 *   - context: stored bars from the sessions before the replay day, dimmed. These are real
 *     stored candles (GET /market/candles with a date range), shown so the first replayed bar
 *     does not float alone; they are not part of the replay.
 *   - replay: the view bars streamed by the session, appended incrementally.
 * Fill markers are drawn on the replay series. Times are shifted to IST like CandleChart.
 */
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import type { Candle, CandlesResponse, Timeframe } from "@/lib/api/generated";
import { api } from "@/lib/api/client";
import { chartPalette, onThemeChange, withAlpha } from "@/lib/theme";
import { TF_SECONDS, type ReplayEvent } from "./useReplayStream";

const IST_OFFSET_S = 5.5 * 3600;
const NSE_OPEN_S = 9 * 3600 + 15 * 60;

/** Snap an IST-shifted 1m time onto the view-timeframe bucket it belongs to (NSE session-aligned). */
function bucketOf(t: UTCTimestamp, tf: Timeframe): UTCTimestamp {
  const dur = TF_SECONDS[tf] ?? 60;
  const open = Math.floor(t / 86400) * 86400 + NSE_OPEN_S;
  if (tf === "1d") return open as UTCTimestamp;
  return (open + Math.floor((t - open) / dur) * dur) as UTCTimestamp;
}

function toTime(iso: string): UTCTimestamp {
  return (Math.floor(new Date(iso).getTime() / 1000) + IST_OFFSET_S) as UTCTimestamp;
}

function toBar(c: Candle): CandlestickData<Time> {
  return { time: toTime(c.ts), open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close) };
}

function toVol(c: Candle, pal: ReturnType<typeof chartPalette>, alpha: number): HistogramData<Time> {
  const up = Number(c.close) >= Number(c.open);
  return { time: toTime(c.ts), value: c.volume, color: withAlpha(up ? pal.up : pal.down, alpha) };
}

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
    timeScale: { borderColor: pal.border, timeVisible: true, secondsVisible: false, rightOffset: 4 },
    crosshair: {
      mode: 0,
      vertLine: { color: pal.crosshair, labelBackgroundColor: pal.crosshairLabel },
      horzLine: { color: pal.crosshair, labelBackgroundColor: pal.crosshairLabel },
    },
  } as const;
}

const dimmed = (pal: ReturnType<typeof chartPalette>) => ({
  upColor: withAlpha(pal.up, 0.35),
  downColor: withAlpha(pal.down, 0.35),
  wickUpColor: withAlpha(pal.up, 0.35),
  wickDownColor: withAlpha(pal.down, 0.35),
  borderVisible: false,
  lastValueVisible: false,
  priceLineVisible: false,
});

/** Stored bars from the ten days before `date` (IST) in the view timeframe, for context. */
export function useContextCandles(instrumentId: number, date: string, timeframe: Timeframe, enabled: boolean) {
  // NSE opens 09:15 IST = 03:45 UTC; everything before that on the replay day is "before".
  const end = `${date}T03:44:00Z`;
  const start = new Date(new Date(`${date}T00:00:00Z`).getTime() - 10 * 86400_000).toISOString();
  return useQuery({
    queryKey: ["replay", "context", instrumentId, date, timeframe],
    queryFn: () =>
      api<CandlesResponse>(
        `/market/candles?instrument_id=${instrumentId}&timeframe=${timeframe}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&limit=400`,
      ),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function ReplayChart({
  bars,
  contextBars,
  events,
  timeframe,
  height = 380,
}: {
  bars: Candle[];
  contextBars: Candle[];
  events: ReplayEvent[];
  timeframe: Timeframe;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const ctxRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const palRef = useRef(chartPalette());
  const appliedRef = useRef<Candle[]>([]);
  const ctxAppliedRef = useRef<Candle[]>([]);
  const fittedRef = useRef(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const pal = chartPalette();
    palRef.current = pal;
    const chart = createChart(el, { height, ...themeOptions(pal) });
    const ctx = chart.addSeries(CandlestickSeries, dimmed(pal));
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
    ctxRef.current = ctx;
    candleRef.current = candle;
    volRef.current = vol;
    markersRef.current = createSeriesMarkers(candle, []);
    appliedRef.current = [];
    ctxAppliedRef.current = [];
    fittedRef.current = false;
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    ro.observe(el);
    const offTheme = onThemeChange(() => {
      const next = chartPalette();
      palRef.current = next;
      chart.applyOptions(themeOptions(next));
      ctx.applyOptions(dimmed(next));
      candle.applyOptions({ upColor: next.up, downColor: next.down, wickUpColor: next.up, wickDownColor: next.down, priceLineColor: next.priceLine });
      vol.setData([
        ...ctxAppliedRef.current.map((c) => toVol(c, next, 0.18)),
        ...appliedRef.current.map((c) => toVol(c, next, 0.45)),
      ]);
    });
    return () => {
      offTheme();
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      ctxRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      markersRef.current = null;
    };
  }, [height]);

  // Context series: set once per load.
  useEffect(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    ctxAppliedRef.current = contextBars;
    ctx.setData(contextBars.map(toBar));
    volRef.current?.setData([
      ...contextBars.map((c) => toVol(c, palRef.current, 0.18)),
      ...appliedRef.current.map((c) => toVol(c, palRef.current, 0.45)),
    ]);
    if (contextBars.length && !fittedRef.current) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [contextBars]);

  // Replay series: append when `bars` extends what is already drawn, otherwise reset.
  useEffect(() => {
    const s = candleRef.current;
    const v = volRef.current;
    if (!s || !v) return;
    const prev = appliedRef.current;
    const extends_ =
      bars.length >= prev.length && prev.every((c, i) => bars[i] === c || bars[i]?.ts === c.ts);
    if (extends_ && prev.length) {
      for (let i = prev.length - 1; i < bars.length; i++) {
        const c = bars[i];
        if (!c) continue;
        s.update(toBar(c));
        v.update(toVol(c, palRef.current, 0.45));
      }
    } else {
      s.setData(bars.map(toBar));
      v.setData([
        ...ctxAppliedRef.current.map((c) => toVol(c, palRef.current, 0.18)),
        ...bars.map((c) => toVol(c, palRef.current, 0.45)),
      ]);
    }
    appliedRef.current = bars;
    if (bars.length && !fittedRef.current) {
      // First replay bar: show the tail of the context plus room for the day's bars.
      fittedRef.current = true;
      const n = ctxAppliedRef.current.length;
      chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 60), to: n + 90 });
    }
  }, [bars]);

  // Fill markers on the replay series.
  useEffect(() => {
    const m = markersRef.current;
    if (!m) return;
    const pal = palRef.current;
    const markers: SeriesMarker<Time>[] = events
      .filter((e) => e.kind === "fill")
      .map((e) => {
        const f = e.kind === "fill" ? e.data : null;
        const buy = f?.side === "buy";
        return {
          time: bucketOf(toTime(e.ts), timeframe),
          position: buy ? "belowBar" : "aboveBar",
          shape: buy ? "arrowUp" : "arrowDown",
          color: buy ? pal.up : pal.down,
          text: `${buy ? "B" : "S"} ${f?.quantity ?? ""} @ ${f ? Number(f.price).toFixed(2) : ""}`,
          size: 1,
        } as SeriesMarker<Time>;
      })
      .sort((a, b) => (a.time as number) - (b.time as number));
    m.setMarkers(markers);
  }, [events, timeframe]);

  return <div ref={containerRef} className="w-full" />;
}
