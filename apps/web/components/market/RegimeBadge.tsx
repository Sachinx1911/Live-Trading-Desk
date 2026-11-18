"use client";

import type { ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type {
  RegimeDaily,
  RegimeDayType,
  RegimeIntraday,
  RegimeStrength,
  RegimeStructure,
  RegimeTrend,
  RegimeVolatility,
  TradeRegime,
} from "@/lib/api/generated";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

/*
 * Regime labels as 20px pills (reference §5). Colour carries meaning, never decoration:
 * trend up/down = P&L colours, sideways = muted; high volatility = warn, low = accent tint;
 * event day = AI purple tint so it stands apart from price colours.
 */

const TREND: Record<RegimeTrend, { label: string; cls: string }> = {
  up: { label: "Uptrend", cls: "bg-up-soft text-up" },
  down: { label: "Downtrend", cls: "bg-down-soft text-down" },
  sideways: { label: "Sideways", cls: "bg-raised text-text-3" },
};
const STRENGTH: Record<RegimeStrength, string> = { weak: "weak", moderate: "moderate", strong: "strong" };
const VOL: Record<RegimeVolatility, { label: string; cls: string }> = {
  low: { label: "Low vol", cls: "bg-accent-soft text-accent-text" },
  normal: { label: "Normal vol", cls: "bg-raised text-text-2" },
  high: { label: "High vol", cls: "bg-warn-soft text-warn" },
};
const STRUCT: Record<RegimeStructure, { label: string; cls: string }> = {
  bullish: { label: "HH·HL", cls: "bg-raised text-up" },
  bearish: { label: "LH·LL", cls: "bg-raised text-down" },
  range: { label: "Range", cls: "bg-raised text-text-3" },
};
const DAY: Record<RegimeDayType, { label: string; cls: string }> = {
  trending: { label: "Trending day", cls: "bg-raised text-text-1" },
  range: { label: "Range day", cls: "bg-raised text-text-3" },
  volatile_open: { label: "Volatile open", cls: "bg-warn-soft text-warn" },
  unknown: { label: "Day type —", cls: "bg-raised text-text-3" },
};

export function Pill({ className, children, title }: { className?: string; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 text-[11px] font-medium uppercase tracking-wide whitespace-nowrap", className)}
    >
      {children}
    </span>
  );
}

function n(v: number | null | undefined, digits = 1) {
  return v == null ? "—" : formatNumber(v, digits);
}

/** Tooltip body: the numbers behind the labels, so nobody has to trust a word alone. */
export function RegimeNumbers({ d, intraday }: { d: RegimeDaily; intraday?: RegimeIntraday | null }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px] tabular">
      <span className="text-text-3">ADX</span>
      <span>{n(d.adx)}</span>
      <span className="text-text-3">VIX</span>
      <span>
        {n(d.vix, 2)}
        {d.vix_percentile != null && <span className="text-text-3"> · {formatNumber(d.vix_percentile, 0)}th pct (1y)</span>}
      </span>
      <span className="text-text-3">ATR %</span>
      <span>{n(d.atr_pct, 2)}</span>
      <span className="text-text-3">EMA 20/50/200</span>
      <span>
        {n(d.ema20)} / {n(d.ema50)} / {n(d.ema200)}
      </span>
      {intraday && (
        <>
          <span className="text-text-3">Opening range</span>
          <span>
            {n(intraday.or_low)} – {n(intraday.or_high)}
          </span>
          <span className="text-text-3">VWAP dist.</span>
          <span>{intraday.vwap_distance_pct == null ? "—" : `${formatNumber(intraday.vwap_distance_pct, 2)}%`}</span>
          <span className="text-text-3">ATR ratio</span>
          <span>{n(intraday.atr_ratio, 2)}</span>
        </>
      )}
      {d.events.length > 0 && (
        <>
          <span className="text-text-3">Events</span>
          <span>{d.events.join(", ")}</span>
        </>
      )}
      <span className="text-text-3">Computed</span>
      <span>{formatDateTime(d.computed_at)}</span>
    </div>
  );
}

function WithTip({ tip, children }: { tip: ReactNode; children: ReactNode }) {
  if (!tip) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger render={<span className="inline-flex" />}>{children}</TooltipTrigger>
      <TooltipContent className="max-w-sm">{tip}</TooltipContent>
    </Tooltip>
  );
}

export function TrendBadge({ d, withStrength = true, tip }: { d: Pick<RegimeDaily, "trend" | "strength">; withStrength?: boolean; tip?: ReactNode }) {
  const t = TREND[d.trend];
  return (
    <WithTip tip={tip}>
      <Pill className={t.cls}>
        {t.label}
        {withStrength && <span className="opacity-70">· {STRENGTH[d.strength]}</span>}
      </Pill>
    </WithTip>
  );
}

export function VolBadge({ v, tip }: { v: RegimeVolatility; tip?: ReactNode }) {
  const c = VOL[v];
  return (
    <WithTip tip={tip}>
      <Pill className={c.cls}>{c.label}</Pill>
    </WithTip>
  );
}

export function StructureBadge({ s, tip }: { s: RegimeStructure; tip?: ReactNode }) {
  const c = STRUCT[s];
  return (
    <WithTip tip={tip}>
      <Pill className={c.cls} title={s}>
        {c.label}
      </Pill>
    </WithTip>
  );
}

export function DayTypeBadge({ t, tip }: { t: RegimeDayType; tip?: ReactNode }) {
  const c = DAY[t];
  return (
    <WithTip tip={tip}>
      <Pill className={c.cls}>{c.label}</Pill>
    </WithTip>
  );
}

export function EventBadge({ events }: { events: string[] }) {
  return (
    <Pill className="bg-ai-soft text-ai" title={events.join(", ") || "Event day"}>
      Event
    </Pill>
  );
}

/** Full label row for one day (+ optional intraday). Numbers live in the tooltips. */
export function RegimeBadges({ d, intraday, compact = false }: { d: RegimeDaily; intraday?: RegimeIntraday | null; compact?: boolean }) {
  const tip = <RegimeNumbers d={d} intraday={intraday} />;
  return (
    <div className="flex flex-wrap items-center gap-1">
      <TrendBadge d={d} withStrength={!compact} tip={tip} />
      <VolBadge v={d.volatility} tip={tip} />
      {!compact && <StructureBadge s={d.structure} tip={tip} />}
      {intraday && <DayTypeBadge t={intraday.day_type} tip={tip} />}
      {d.event_day && <EventBadge events={d.events} />}
    </div>
  );
}

/** Tiny pills for a trade's stored regime tag; "—" when the trade predates tagging. */
export function TradeRegimePills({ r }: { r: TradeRegime | null | undefined }) {
  if (!r || (!r.trend && !r.volatility && !r.day_type)) return <span className="text-text-3">—</span>;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {r.trend && TREND[r.trend] && <Pill className={cn("h-4 px-1.5 text-[10px]", TREND[r.trend].cls)}>{TREND[r.trend].label}</Pill>}
      {r.volatility && VOL[r.volatility] && <Pill className={cn("h-4 px-1.5 text-[10px]", VOL[r.volatility].cls)}>{VOL[r.volatility].label}</Pill>}
      {r.day_type && DAY[r.day_type] && <Pill className={cn("h-4 px-1.5 text-[10px]", DAY[r.day_type].cls)}>{DAY[r.day_type].label}</Pill>}
    </div>
  );
}

/** Colour of a history cell: trend decides the hue, strength the intensity. */
export function trendCellClass(d: RegimeDaily): string {
  const base = d.trend === "up" ? "bg-up" : d.trend === "down" ? "bg-down" : "bg-text-3";
  const alpha = d.strength === "strong" ? "" : d.strength === "moderate" ? "opacity-70" : "opacity-40";
  return cn(base, alpha);
}

export const TREND_LABEL = (t: RegimeTrend) => TREND[t].label;
export const VOL_LABEL = (v: RegimeVolatility) => VOL[v].label;
export const DAY_LABEL = (t: RegimeDayType) => DAY[t].label;
export const STRUCT_LABEL = (s: RegimeStructure) => STRUCT[s].label;
