"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { InstrumentSearch, instrumentLabel } from "@/components/market/InstrumentSearch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiRequestError } from "@/lib/api/client";
import type { Instrument, ReplaySessionIn, StrategyVersion, Timeframe } from "@/lib/api/generated";
import { useStrategies, useStrategyVersions } from "@/lib/api/trading";

const SEL = "h-8 border border-border bg-raised px-2 text-xs";
const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1h"];
export const SPEEDS: { x: number; label: string }[] = [
  { x: 1, label: "1× (real time)" },
  { x: 10, label: "10×" },
  { x: 60, label: "60× (1 min/s)" },
  { x: 300, label: "300×" },
];

/** YYYY-MM-DD of a Date in IST. */
export function isoDayIST(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

/**
 * Most recent weekday strictly before today (IST). Exchange holidays are not known here; the
 * API answers 400 for a non-trading day and the form shows that message.
 */
export function lastTradingDayGuess(now = new Date()): string {
  const d = new Date(now.getTime());
  do {
    d.setUTCDate(d.getUTCDate() - 1);
  } while ([0, 6].includes(new Date(`${isoDayIST(d)}T00:00:00Z`).getUTCDay()));
  return isoDayIST(d);
}

/** Strategy versions grouped by strategy, excluding rejected ones. */
function VersionSelect({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (v: StrategyVersion | null) => void;
}) {
  const { data: strategies } = useStrategies(false);
  const [strategyId, setStrategyId] = useState<number | null>(null);
  const { data: versions } = useStrategyVersions(strategyId);
  const eligible = (versions ?? []).filter((v) => v.status !== "rejected");
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rp-strategy">Strategy (optional)</Label>
        <select
          id="rp-strategy"
          value={strategyId ?? ""}
          onChange={(e) => {
            setStrategyId(e.target.value ? Number(e.target.value) : null);
            onChange(null);
          }}
          className={SEL}
        >
          <option value="">None · bars only</option>
          {strategies?.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
      {strategyId != null && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rp-version">Version</Label>
          <select
            id="rp-version"
            value={value ?? ""}
            onChange={(e) => onChange(eligible.find((v) => v.id === Number(e.target.value)) ?? null)}
            className={SEL}
          >
            <option value="">Select a version…</option>
            {eligible.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.version_no} · {v.status}{v.change_summary ? ` · ${v.change_summary}` : ""}
              </option>
            ))}
          </select>
          {versions && eligible.length === 0 && <p className="text-[11px] text-text-3">This strategy has no usable version.</p>}
        </div>
      )}
    </>
  );
}

export function ReplaySetupForm({
  onStart,
  isPending,
  error,
  initialInstrument,
}: {
  onStart: (body: ReplaySessionIn, instrument: Instrument, version: StrategyVersion | null) => void;
  isPending: boolean;
  error: unknown;
  initialInstrument?: Instrument | null;
}) {
  const [instrument, setInstrument] = useState<Instrument | null>(initialInstrument ?? null);
  const [date, setDate] = useState(lastTradingDayGuess());
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");
  const [version, setVersion] = useState<StrategyVersion | null>(null);
  const [speed, setSpeed] = useState(60);
  const err = error instanceof ApiRequestError ? error.message : error ? "Cannot reach the API." : null;
  const dslTf = version ? String((version.dsl as { timeframe?: string }).timeframe ?? "") : "";

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!instrument) return;
        onStart(
          {
            instrument_id: instrument.instrument_id,
            date,
            timeframe,
            strategy_version_id: version?.id ?? null,
            speed,
          },
          instrument,
          version,
        );
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label>Instrument</Label>
        {instrument ? (
          <div className="flex items-center justify-between border border-border bg-raised px-2 py-1.5 text-xs">
            <span className="truncate">
              {instrumentLabel(instrument)} <span className="text-text-3">· {instrument.exchange} · {instrument.segment}</span>
            </span>
            <Button type="button" size="xs" variant="ghost" onClick={() => setInstrument(null)}>change</Button>
          </div>
        ) : (
          <InstrumentSearch onPick={setInstrument} placeholder="Search NIFTY, BANKNIFTY, RELIANCE…" autoFocus />
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rp-date">Trading day (IST)</Label>
          <Input id="rp-date" type="date" value={date} max={isoDayIST(new Date())} onChange={(e) => setDate(e.target.value)} className="h-8 text-xs tabular" required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rp-tf">Chart timeframe</Label>
          <select id="rp-tf" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)} className={SEL}>
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </div>
      </div>
      <VersionSelect value={version?.id ?? null} onChange={setVersion} />
      {version && dslTf && dslTf !== timeframe && (
        <p className="text-[11px] text-text-3">The strategy evaluates on its own {dslTf} bars; the chart shows {timeframe}.</p>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rp-speed">Speed</Label>
        <select id="rp-speed" value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className={SEL}>
          {SPEEDS.map((s) => <option key={s.x} value={s.x}>{s.label}</option>)}
        </select>
      </div>
      {err && <p className="text-[11px] text-down">{err}</p>}
      <Button type="submit" variant="primary" disabled={!instrument || !date || isPending}>
        <Play /> Start replay
      </Button>
      <p className="text-[11px] text-text-3">
        Replays the stored 1-minute candles of one trading day. With a strategy attached, the same engine, risk rules and simulator as paper trading run on ₹1,00,000 of virtual capital, in memory only. Nothing is persisted and no account is touched.
      </p>
    </form>
  );
}
