"use client";

import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DslCatalogue } from "@/lib/api/generated";
import { REGIME_SOURCES, TIME_FILTER_MODES, WEEKDAYS } from "@/lib/dsl-catalogue-fallback";
import type { DslDoc, RegimeFilter, TimeFilter } from "@/lib/dsl/types";
import { Field, NumberInput, Row, Section, Select, TextInput, TimeInput } from "./fields";

export function SessionSection({ doc, onChange, catalogue }: { doc: DslDoc; onChange: (p: Partial<DslDoc>) => void; catalogue: DslCatalogue }) {
  const s = doc.session;
  const setS = (p: Partial<DslDoc["session"]>) => onChange({ session: { ...s, ...p } });
  const days = s.allowed_weekdays ?? [0, 1, 2, 3, 4];
  const indicatorIds = Object.keys(doc.indicators);

  const setTF = (i: number, p: Partial<TimeFilter>) => onChange({ time_filters: doc.time_filters.map((t, j) => (j === i ? { ...t, ...p } : t)) });
  const setRF = (i: number, p: Partial<RegimeFilter>) => onChange({ regime_filters: doc.regime_filters.map((r, j) => (j === i ? { ...r, ...p } : r)) });

  return (
    <Section title="Session" subtitle="product, trading window, filters">
      <Row>
        <Field label="Product">
          <Select value={s.product} options={catalogue.products} onChange={(v) => setS({ product: v })} />
        </Field>
        <Field label="Trade start">
          <TimeInput value={s.trade_start} onChange={(v) => setS({ trade_start: v })} />
        </Field>
        <Field label="No new entries after">
          <TimeInput value={s.no_new_entries_after} onChange={(v) => setS({ no_new_entries_after: v })} />
        </Field>
        <Field label="Square off at">
          <TimeInput value={s.square_off_at} onChange={(v) => setS({ square_off_at: v })} />
        </Field>
        <Field label="Skip first minutes">
          <NumberInput value={s.skip_first_minutes ?? 0} min={0} step={1} onChange={(v) => setS({ skip_first_minutes: v ?? 0 })} />
        </Field>
        <Field label="Weekdays">
          <div className="flex gap-0.5">
            {WEEKDAYS.map((d, i) => {
              const on = days.includes(i);
              return (
                <button
                  key={d}
                  type="button"
                  onClick={() => setS({ allowed_weekdays: on ? days.filter((x) => x !== i) : [...days, i].sort() })}
                  className={on ? "h-7 border border-accent bg-accent/15 px-1.5 text-[11px] text-text-1" : "h-7 border border-border bg-raised px-1.5 text-[11px] text-text-3"}
                >
                  {d}
                </button>
              );
            })}
          </div>
        </Field>
      </Row>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-text-3">Time filters</span>
          <Button size="xs" variant="ghost" onClick={() => onChange({ time_filters: [...doc.time_filters, { start: "11:30", end: "13:00", mode: "block_entries" }] })}><Plus /> Add window</Button>
        </div>
        {doc.time_filters.length === 0 && <span className="text-[11px] text-text-3">None — entries allowed throughout the session window.</span>}
        {doc.time_filters.map((t, i) => (
          <Row key={i} className="items-center">
            <Select value={t.mode} options={TIME_FILTER_MODES} labels={{ allow_entries: "Allow entries only", block_entries: "Block entries" }} onChange={(v) => setTF(i, { mode: v })} />
            <TimeInput value={t.start} onChange={(v) => setTF(i, { start: v ?? "" })} />
            <span className="text-[11px] text-text-3">to</span>
            <TimeInput value={t.end} onChange={(v) => setTF(i, { end: v ?? "" })} />
            <Button size="icon-xs" variant="ghost" aria-label="Remove time filter" onClick={() => onChange({ time_filters: doc.time_filters.filter((_, j) => j !== i) })}><X /></Button>
          </Row>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-text-3">Regime filters</span>
          <Button size="xs" variant="ghost" onClick={() => onChange({ regime_filters: [...doc.regime_filters, { source: "vix", min: null, max: 20 }] })}><Plus /> Add filter</Button>
        </div>
        {doc.regime_filters.length === 0 && <span className="text-[11px] text-text-3">None — trades in every regime.</span>}
        {doc.regime_filters.map((r, i) => (
          <Row key={i} className="items-center">
            <Select value={r.source} options={REGIME_SOURCES} labels={{ vix: "India VIX", adx: "ADX indicator", daily_trend: "Daily trend label", regime_label: "Market regime label" }} onChange={(v) => setRF(i, { source: v, allowed: v === "daily_trend" || v === "regime_label" ? (r.allowed ?? []) : null, indicator_id: v === "adx" || v === "daily_trend" ? (r.indicator_id ?? indicatorIds[0] ?? "") : null })} />
            {(r.source === "adx" || r.source === "daily_trend") && (
              <Select value={r.indicator_id} allowBlank="indicator…" options={indicatorIds} onChange={(v) => setRF(i, { indicator_id: v })} />
            )}
            {(r.source === "vix" || r.source === "adx") && (
              <>
                <NumberInput value={r.min} allowBlank placeholder="min" onChange={(v) => setRF(i, { min: v })} />
                <NumberInput value={r.max} allowBlank placeholder="max" onChange={(v) => setRF(i, { max: v })} />
              </>
            )}
            {(r.source === "daily_trend" || r.source === "regime_label") && (
              <TextInput value={(r.allowed ?? []).join(",")} placeholder="allowed labels, comma separated (e.g. up,flat)" className="w-72" onChange={(v) => setRF(i, { allowed: v.split(",").map((x) => x.trim()).filter(Boolean) })} />
            )}
            <Button size="icon-xs" variant="ghost" aria-label="Remove regime filter" onClick={() => onChange({ regime_filters: doc.regime_filters.filter((_, j) => j !== i) })}><X /></Button>
          </Row>
        ))}
      </div>
    </Section>
  );
}
