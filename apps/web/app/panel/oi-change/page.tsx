"use client";

import { Suspense, useMemo } from "react";
import { DemoBanner } from "@/components/design";
import { OiChangeChart } from "@/components/market/OiChangeChart";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { istToday, useElementSize, useInstrumentBySymbol, usePanelParams } from "@/components/panels/usePanel";
import { ApiRequestError } from "@/lib/api/client";
import { useOiChange, useOiChangeExpiries } from "@/lib/api/queries";
import { formatNumber, formatTime } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";
import { cn } from "@/lib/utils";

const OPEN = "09:15";
const CLOSE = "15:30";

function signed(v: number): string {
  return `${v > 0 ? "+" : ""}${formatNumber(v)}`;
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="hud-panel hud-frame min-w-0 rounded-[var(--r-sm)] border border-border bg-pane px-3 py-2">
      <p className="hud-label truncate text-text-3">{label}</p>
      <p className={cn("tabular truncate font-mono text-[clamp(18px,3.2vw,40px)] leading-tight font-semibold text-text-1", tone)}>{value}</p>
      {sub && <p className="truncate text-[11px] text-text-3">{sub}</p>}
    </div>
  );
}

function OiChangePanel() {
  const { values, errors: paramErrors } = usePanelParams("oi-change");
  const symbol = values.symbol;
  const day = values.date ?? istToday();
  const start = values.from ?? OPEN;
  const end = values.to ?? CLOSE;
  const range = values.range != null ? Number(values.range) : 10;
  const errors = [...paramErrors];
  if (!errors.some((e) => e.param === "from" || e.param === "to") && start >= end) errors.push({ param: "to", message: `${end} is not after from=${start}` });
  if (values.date && values.date > istToday()) errors.push({ param: "date", message: `${values.date} is in the future` });

  const inst = useInstrumentBySymbol(errors.length ? undefined : symbol);
  const id = inst.data?.instrument_id ?? null;
  const expiries = useOiChangeExpiries(id, day);
  const known = expiries.data ?? [];
  const expiry = values.expiry ?? known[0];
  const expiryUnknown = values.expiry != null && expiries.isSuccess && !known.includes(values.expiry);
  const q = useOiChange(expiryUnknown ? null : id, expiry, day, start, end);
  const data = q.data;
  const notFound = q.error instanceof ApiRequestError && q.error.status === 404;
  const [chartRef, chartSize] = useElementSize<HTMLDivElement>();

  const spot = data?.spot_to != null ? Number(data.spot_to) : null;
  const shown = useMemo(() => {
    const rows = data?.strikes ?? [];
    if (!range || spot == null || rows.length === 0) return rows;
    const idx = rows.reduce((best, s, i) => (Math.abs(Number(s.strike) - spot) < Math.abs(Number(rows[best].strike) - spot) ? i : best), 0);
    return rows.slice(Math.max(0, idx - range), idx + range + 1);
  }, [data, range, spot]);

  const subtitle = symbol ? `${symbol} · ${day} · ${start}→${end}${expiry ? ` · exp ${expiry}` : ""}` : undefined;
  const frame = (children: React.ReactNode, state?: Parameters<typeof PanelFrame>[0]["state"]) => (
    <PanelFrame
      panel="oi-change"
      subtitle={subtitle}
      state={state}
      source={data ? `${data.source} · ${formatTime(data.from_ts)}→${formatTime(data.to_ts)}` : undefined}
      fullHref={fullPageUrl("oi-change")}
      bodyClassName="flex flex-col"
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="oi-change" errors={errors} />);
  if (inst.isPending) return frame(<PanelMessage title={`Resolving ${symbol}…`} />);
  if (inst.isError) return frame(<PanelMessage tone="error" title="Cannot reach the API" />, "disconnected");
  if (!inst.data) return frame(<PanelMessage tone="error" title={`symbol: ${symbol} not found`} description="No such index in the instrument master." />);
  if (expiries.isPending) return frame(<PanelMessage title="Loading stored expiries…" />);
  if (expiryUnknown)
    return frame(
      <PanelMessage
        tone="error"
        title={`expiry: nothing stored for ${values.expiry} on ${day}`}
        description={known.length ? `Expiries stored that day: ${known.join(", ")}` : "No option-chain snapshot stored that day."}
      />,
    );
  if (!expiry)
    return frame(
      <PanelMessage title={`No option chain stored for ${symbol} on ${day}`} description="Snapshots are stored only while the collector runs during market hours. Pick another date." />,
      "disconnected",
    );
  if (notFound)
    return frame(<PanelMessage title={`No snapshots between ${start} and ${end}`} description="The collector stores the chain every few minutes while it runs. Pick another window." />, "disconnected");
  if (q.isError) return frame(<PanelMessage tone="error" title="Could not load OI change" description={q.error.message} />, "disconnected");
  if (!data) return frame(<PanelMessage title="Loading…" />);

  return frame(
    <>
      {data.freshness === "demo" && <DemoBanner />}
      <div className="grid shrink-0 grid-cols-2 gap-2 p-2 md:grid-cols-4">
        <Stat label="Call OI change" value={signed(data.call_oi_change_total)} tone="text-accent-text" />
        <Stat label="Put OI change" value={signed(data.put_oi_change_total)} tone="text-amber" />
        <Stat label="PCR" value={data.pcr_to != null ? Number(data.pcr_to).toFixed(2) : "—"} sub={data.pcr_from != null ? `from ${Number(data.pcr_from).toFixed(2)}` : "no call OI at the start"} />
        <Stat
          label={`${symbol} spot`}
          value={data.spot_to != null ? formatNumber(Number(data.spot_to), 2) : "—"}
          sub={data.spot_from != null ? `from ${formatNumber(Number(data.spot_from), 2)}` : undefined}
        />
      </div>
      <div className="flex shrink-0 items-center gap-4 px-3 text-[11px] text-text-3">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 bg-[var(--accent)]" aria-hidden /> Calls
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 bg-[var(--hud-amber)]" aria-hidden /> Puts
        </span>
        <span className="truncate">Up = OI added · down = unwound · shaded = ATM</span>
      </div>
      <div ref={chartRef} className="min-h-[160px] flex-1 overflow-hidden px-2 pb-2">
        {shown.length === 0 ? (
          <PanelMessage title="No strikes in this window" />
        ) : (
          chartSize.width > 0 && <OiChangeChart strikes={shown} atm={spot} width={chartSize.width} height={Math.max(160, chartSize.height - 12)} />
        )}
      </div>
    </>,
    data.freshness,
  );
}

export default function OiChangePanelPage() {
  return (
    <Suspense>
      <OiChangePanel />
    </Suspense>
  );
}
