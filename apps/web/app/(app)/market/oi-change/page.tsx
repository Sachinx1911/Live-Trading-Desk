"use client";

import { useEffect, useMemo, useState } from "react";
import { DataStateBadge, DemoBanner, EmptyState, PanelCard } from "@/components/design";
import { OiChangeChart } from "@/components/market/OiChangeChart";
import { api, ApiRequestError } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { useOiChange, useOiChangeExpiries } from "@/lib/api/queries";
import { formatNumber, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/*
 * OI Change (Mark 1, 1.2): per-strike call/put OI change between two moments of one day,
 * from stored chain snapshots of the active provider. Shows the snapshot times actually used,
 * so a gap to the requested time is visible; nothing is interpolated.
 */

const UNDERLYINGS = ["NIFTY", "BANKNIFTY"];
const OPEN = "09:15";
const CLOSE = "15:30";
const RANGES = [5, 10, 15, 0] as const; // strikes each side of spot; 0 = all

function istToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

function istNowHHMM(): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function minus(hhmm: string, minutes: number): string {
  const [h, m] = hhmm.split(":").map(Number);
  const t = Math.max(h * 60 + m - minutes, 9 * 60 + 15);
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

function signed(v: number): string {
  return `${v > 0 ? "+" : ""}${formatNumber(v)}`;
}

export default function OiChangePage() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [ids, setIds] = useState<Record<string, number>>({});
  const [day, setDay] = useState(istToday);
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const [start, setStart] = useState(OPEN);
  const [end, setEnd] = useState(CLOSE);
  const [range, setRange] = useState<number>(10);
  const id = ids[symbol] ?? null;

  useEffect(() => {
    let alive = true;
    void (async () => {
      const out: Record<string, number> = {};
      for (const sym of UNDERLYINGS) {
        try {
          const hits = await api<Instrument[]>(`/instruments?q=${sym}&exchange=NSE&limit=20`);
          const hit =
            hits.find((i) => i.symbol === sym && i.segment === "index") ?? hits.find((i) => i.symbol === sym);
          if (hit) out[sym] = hit.instrument_id;
        } catch {
          /* shown as unresolved */
        }
      }
      if (alive) setIds(out);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const expiries = useOiChangeExpiries(id, day);
  const effectiveExpiry = expiry && expiries.data?.includes(expiry) ? expiry : expiries.data?.[0];
  const q = useOiChange(id, effectiveExpiry, day, start, end);
  const data = q.data;

  const spot = data?.spot_to != null ? Number(data.spot_to) : null;
  const shown = useMemo(() => {
    const rows = data?.strikes ?? [];
    if (!range || spot == null || rows.length === 0) return rows;
    const idx = rows.reduce(
      (best, s, i) => (Math.abs(Number(s.strike) - spot) < Math.abs(Number(rows[best].strike) - spot) ? i : best),
      0,
    );
    return rows.slice(Math.max(0, idx - range), idx + range + 1);
  }, [data, range, spot]);

  const isToday = day === istToday();
  const presets: { label: string; s: string; e: string }[] = [
    { label: "Full day", s: OPEN, e: CLOSE },
    ...[15, 30, 60].map((m) => {
      const e = isToday ? istNowHHMM() : CLOSE;
      return { label: `Last ${m}m`, s: minus(e, m), e };
    }),
  ];

  const notFound = q.error instanceof ApiRequestError && q.error.status === 404;

  return (
    <div className="flex flex-col gap-3">
      <PanelCard title="OI Change" subtitle="Per-strike open interest change between two times" bodyClassName="flex flex-wrap items-center gap-3 p-2">
        <div className="flex rounded-[var(--r-sm)] border border-border">
          {UNDERLYINGS.map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => {
                setSymbol(u);
                setExpiry(undefined);
              }}
              className={cn("hud-label px-3 py-1", u === symbol ? "bg-accent-soft text-accent-text" : "text-text-3 hover:text-text-2")}
            >
              {u}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-text-2">
          Day
          <input
            type="date"
            value={day}
            max={istToday()}
            onChange={(e) => {
              setDay(e.target.value || istToday());
              setExpiry(undefined);
            }}
            className="h-7 border border-border bg-pane px-2 text-xs text-text-1"
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-text-2">
          Expiry
          <select
            value={effectiveExpiry ?? ""}
            onChange={(e) => setExpiry(e.target.value || undefined)}
            className="h-7 border border-border bg-pane px-2 text-xs text-text-1"
            disabled={!expiries.data?.length}
          >
            {!expiries.data?.length && <option value="">No snapshots that day</option>}
            {expiries.data?.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-text-2">
          From
          <input type="time" value={start} onChange={(e) => setStart(e.target.value || OPEN)} className="h-7 border border-border bg-pane px-2 text-xs text-text-1" />
        </label>
        <label className="flex items-center gap-2 text-xs text-text-2">
          To
          <input type="time" value={end} onChange={(e) => setEnd(e.target.value || CLOSE)} className="h-7 border border-border bg-pane px-2 text-xs text-text-1" />
        </label>
        <div className="flex gap-1">
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => {
                setStart(p.s);
                setEnd(p.e);
              }}
              className={cn(
                "rounded-[var(--r-pill)] border border-border px-2 py-0.5 text-[11px]",
                start === p.s && end === p.e ? "bg-accent-soft text-accent-text" : "text-text-3 hover:text-text-1",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-text-2">
          Strikes
          <select value={range} onChange={(e) => setRange(Number(e.target.value))} className="h-7 border border-border bg-pane px-2 text-xs text-text-1">
            {RANGES.map((r) => (
              <option key={r} value={r}>
                {r ? `ATM ± ${r}` : "All"}
              </option>
            ))}
          </select>
        </label>
        {id == null && <span className="text-[11px] text-text-3">{symbol} not found in the instrument master yet.</span>}
      </PanelCard>

      {data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Call OI change" value={signed(data.call_oi_change_total)} tone="text-accent-text" />
          <Stat label="Put OI change" value={signed(data.put_oi_change_total)} tone="text-amber" />
          <Stat
            label="PCR"
            value={data.pcr_to != null ? Number(data.pcr_to).toFixed(2) : "—"}
            sub={data.pcr_from != null ? `from ${Number(data.pcr_from).toFixed(2)}` : "no call OI at the start"}
          />
          <Stat
            label={`${symbol} spot`}
            value={data.spot_to != null ? formatNumber(Number(data.spot_to), 2) : "—"}
            sub={data.spot_from != null ? `from ${formatNumber(Number(data.spot_from), 2)}` : undefined}
          />
        </div>
      )}

      <PanelCard
        title={`${symbol} · OI change by strike`}
        subtitle={
          data
            ? `snapshots ${formatTime(data.from_ts)} → ${formatTime(data.to_ts)} (asked ${start} → ${end}) · source ${data.source}`
            : undefined
        }
        actions={data && <DataStateBadge state={data.freshness} />}
        banner={data?.freshness === "demo" ? <DemoBanner /> : undefined}
      >
        {q.isLoading && <p className="text-[13px] text-text-3">Loading…</p>}
        {notFound && (
          <EmptyState
            title="No snapshots in this window"
            description="The collector stores the option chain every few minutes while it runs. Pick another time, day or expiry."
          />
        )}
        {!effectiveExpiry && !expiries.isLoading && (
          <EmptyState title="No option chain stored that day" description="Choose another day, or start the collector." />
        )}
        {q.error && !notFound && <p className="text-[13px] text-down">Could not load: {q.error.message}</p>}
        {data && shown.length > 0 && (
          <>
            <div className="mb-2 flex items-center gap-4 text-[11px] text-text-3">
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 bg-[var(--accent)]" aria-hidden /> Calls
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 bg-[var(--hud-amber)]" aria-hidden /> Puts
              </span>
              <span>Up = OI added · down = OI unwound · shaded = ATM</span>
            </div>
            <OiChangeChart strikes={shown} atm={spot} />
          </>
        )}
      </PanelCard>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="hud-panel hud-frame hud-glow rounded-[var(--r-sm)] border border-border bg-pane p-3">
      <p className="hud-label text-text-3">{label}</p>
      <p className={cn("tabular font-mono text-[32px] leading-10 font-semibold text-text-1", tone)}>{value}</p>
      {sub && <p className="text-[12px] text-text-3">{sub}</p>}
    </div>
  );
}
