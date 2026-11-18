"use client";

import {
  AreaSeries,
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";
import { EmptyState } from "@/components/design";
import type { Point } from "@/lib/backtest-utils";
import { chartPalette, onThemeChange } from "@/lib/theme";
import { cn } from "@/lib/utils";

const IST_OFFSET_S = 5.5 * 3600;

function toTime(iso: string): UTCTimestamp {
  return (Math.floor(new Date(iso).getTime() / 1000) + IST_OFFSET_S) as UTCTimestamp;
}

export interface CurveSeries {
  id: string;
  label?: string;
  points: Point[];
  color?: string;
  area?: boolean;
}

const PALETTE = ["#2962ff", "#a78bfa", "#089981", "#ff9800", "#f23645", "#5b9cf6"];

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

/** Line/area chart for equity and drawdown curves. Times are shifted to IST like CandleChart. */
export function CurveChart({
  series,
  height = 260,
  className,
  emptyTitle = "No curve data",
  priceFormat = "price",
}: {
  series: CurveSeries[];
  height?: number;
  className?: string;
  emptyTitle?: string;
  priceFormat?: "price" | "percent";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line" | "Area">[]>([]);
  const hasData = series.some((s) => s.points.length > 1);

  useEffect(() => {
    const el = ref.current;
    if (!el || !hasData) return;
    const chart = createChart(el, {
      height,
      ...themeOptions(chartPalette()),
      localization: priceFormat === "percent" ? { priceFormatter: (p: number) => `${p.toFixed(2)}%` } : undefined,
    });
    const offTheme = onThemeChange(() => chart.applyOptions(themeOptions(chartPalette())));
    chartRef.current = chart;
    seriesRef.current = series.map((s, idx) => {
      const color = s.color ?? PALETTE[idx % PALETTE.length];
      const api = s.area
        ? chart.addSeries(AreaSeries, { lineColor: color, topColor: `${color}55`, bottomColor: `${color}08`, lineWidth: 1, priceLineVisible: false })
        : chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false });
      // dedupe + sort by time (lightweight-charts rejects out-of-order times)
      const seen = new Map<number, number>();
      for (const p of s.points) seen.set(toTime(p.ts), p.value);
      const data = Array.from(seen.entries())
        .sort((a, b) => a[0] - b[0])
        .map(([t, v]) => ({ time: t as Time, value: v }));
      api.setData(data);
      return api;
    });
    chart.timeScale().fitContent();
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    ro.observe(el);
    return () => {
      offTheme();
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = [];
    };
  }, [series, height, hasData, priceFormat]);

  if (!hasData) return <EmptyState title={emptyTitle} className={className} />;
  return (
    <div className={cn("w-full", className)}>
      {series.length > 1 && (
        <div className="flex flex-wrap gap-3 bg-pane px-3 pt-2 text-[12px]">
          {series.map((s, idx) => (
            <span key={s.id} className="flex items-center gap-1 text-text-2">
              <span className="inline-block size-2 rounded-sm" style={{ background: s.color ?? PALETTE[idx % PALETTE.length] }} />
              {s.label ?? s.id}
            </span>
          ))}
        </div>
      )}
      <div ref={ref} className="w-full bg-pane" />
    </div>
  );
}
