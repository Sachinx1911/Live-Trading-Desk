"use client";

import { X } from "lucide-react";
import { InstrumentSearch, instrumentLabel } from "@/components/market/InstrumentSearch";
import { Button } from "@/components/ui/button";
import type { DslCatalogue, Instrument } from "@/lib/api/generated";
import { CONTRACT_OPTION_TYPES } from "@/lib/dsl-catalogue-fallback";
import type { DslDoc, Universe } from "@/lib/dsl/types";
import { Field, NumberInput, Row, Section, Select, TextInput, Toggle } from "./fields";

const UNIVERSE_LABEL: Record<string, string> = {
  instrument: "Specific instruments",
  underlying_future: "Future of an underlying",
  underlying_option: "Option of an underlying",
  watchlist: "Watchlist",
  scanner: "Scanner output",
};

export function BasicsSection({ doc, onChange, catalogue }: { doc: DslDoc; onChange: (p: Partial<DslDoc>) => void; catalogue: DslCatalogue }) {
  const u = doc.universe;
  const setU = (p: Partial<Universe>) => onChange({ universe: { ...u, ...p } });
  const contract = u.contract ?? { expiry: "current_month", roll_days_before_expiry: 1 };
  const setC = (p: Partial<NonNullable<Universe["contract"]>>) => setU({ contract: { ...contract, ...p } });
  const needsContract = u.kind === "underlying_future" || u.kind === "underlying_option";
  const ctx = doc.context_timeframes;

  return (
    <Section title="Basics" subtitle="name, market, universe, timeframe">
      <Row>
        <Field label="Strategy name" className="min-w-64 flex-1">
          <TextInput value={doc.name} maxLength={80} placeholder="e.g. NIFTY EMA momentum" onChange={(v) => onChange({ name: v })} />
        </Field>
        <Field label="Market">
          <Select value={doc.market} options={["NSE"]} onChange={(v) => onChange({ market: v })} />
        </Field>
        <Field label="Direction">
          <Select value={doc.direction} options={catalogue.directions} labels={{ long_only: "Long only", short_only: "Short only", both: "Both" }} onChange={(v) => onChange({ direction: v })} />
        </Field>
        <Field label="Timeframe">
          <Select value={doc.timeframe} options={catalogue.timeframes} onChange={(v) => onChange({ timeframe: v })} />
        </Field>
        <Field label="Context timeframes" hint="up to 2, for higher-timeframe indicators">
          <div className="flex gap-1">
            {[0, 1].map((i) => (
              <Select
                key={i}
                value={ctx[i] ?? ""}
                allowBlank="—"
                options={catalogue.timeframes}
                onChange={(v) => {
                  const next = [...ctx];
                  if (v) next[i] = v; else next.splice(i, 1);
                  onChange({ context_timeframes: next.filter(Boolean).slice(0, 2) });
                }}
              />
            ))}
          </div>
        </Field>
      </Row>
      <Field label="Description">
        <textarea
          value={doc.description ?? ""}
          onChange={(e) => onChange({ description: e.target.value || null })}
          rows={2}
          placeholder="What the strategy does and when it should not trade"
          className="border border-border bg-raised p-1.5 text-[11px] text-text-1 outline-none focus:border-accent"
        />
      </Field>

      <Row>
        <Field label="Universe">
          <Select
            value={u.kind}
            options={catalogue.universe_kinds}
            labels={UNIVERSE_LABEL}
            onChange={(kind) => {
              const next: Universe = { kind, instrument_ids: kind === "instrument" ? u.instrument_ids : [] };
              if (kind === "underlying_future" || kind === "underlying_option") {
                next.underlying = u.underlying ?? "NIFTY";
                next.contract = { expiry: kind === "underlying_option" ? "current_week" : "current_month", roll_days_before_expiry: 1, ...(kind === "underlying_option" ? { option_type: "CE", strike: "ATM" } : {}) };
              }
              if (kind === "watchlist") next.watchlist_id = u.watchlist_id ?? "";
              if (kind === "scanner") next.scanner_id = u.scanner_id ?? "";
              onChange({ universe: next });
            }}
          />
        </Field>
        {needsContract && (
          <>
            <Field label="Underlying">
              <TextInput value={u.underlying} placeholder="NIFTY" className="w-32 uppercase" onChange={(v) => setU({ underlying: v.toUpperCase() })} />
            </Field>
            <Field label="Expiry">
              <Select value={contract.expiry} options={catalogue.contract_expiries} onChange={(v) => setC({ expiry: v })} />
            </Field>
            {u.kind === "underlying_option" && (
              <>
                <Field label="Type">
                  <Select value={contract.option_type} options={CONTRACT_OPTION_TYPES} onChange={(v) => setC({ option_type: v })} />
                </Field>
                <Field label="Strike">
                  <Select value={contract.strike} options={catalogue.contract_strikes} onChange={(v) => setC({ strike: v })} />
                </Field>
              </>
            )}
            <Field label="Roll days before expiry">
              <NumberInput value={contract.roll_days_before_expiry ?? 1} min={0} max={10} step={1} onChange={(v) => setC({ roll_days_before_expiry: v ?? 1 })} />
            </Field>
          </>
        )}
        {u.kind === "watchlist" && (
          <Field label="Watchlist id">
            <TextInput value={u.watchlist_id} className="w-48" onChange={(v) => setU({ watchlist_id: v })} />
          </Field>
        )}
        {u.kind === "scanner" && (
          <Field label="Scanner id">
            <TextInput value={u.scanner_id} className="w-48" onChange={(v) => setU({ scanner_id: v })} />
          </Field>
        )}
      </Row>

      {u.kind === "instrument" && (
        <div className="flex flex-col gap-2">
          <div className="max-w-md">
            <InstrumentSearch
              placeholder="Search instrument to add…"
              onPick={(i: Instrument) => {
                const id = String(i.instrument_id);
                const labels = { ...((doc.metadata.instrument_labels as Record<string, string> | undefined) ?? {}), [id]: instrumentLabel(i) };
                onChange({
                  universe: { ...u, instrument_ids: u.instrument_ids.includes(id) ? u.instrument_ids : [...u.instrument_ids, id] },
                  metadata: { ...doc.metadata, instrument_labels: labels },
                });
              }}
            />
          </div>
          <div className="flex flex-wrap gap-1">
            {u.instrument_ids.length === 0 && <span className="text-[11px] text-text-3">No instruments yet.</span>}
            {u.instrument_ids.map((id) => {
              const label = ((doc.metadata.instrument_labels as Record<string, string> | undefined) ?? {})[id] ?? id;
              return (
                <span key={id} className="inline-flex h-6 items-center gap-1 border border-border bg-raised pl-2 text-[11px] text-text-1">
                  {label}
                  <Button size="icon-xs" variant="ghost" aria-label={`Remove ${label}`} onClick={() => setU({ instrument_ids: u.instrument_ids.filter((x) => x !== id) })}><X /></Button>
                </span>
              );
            })}
          </div>
        </div>
      )}

      <Row>
        <Field label="Max open positions">
          <NumberInput value={doc.max_positions} min={1} step={1} onChange={(v) => onChange({ max_positions: Math.max(1, v ?? 1) })} />
        </Field>
        <Field label="Max trades / day" hint="blank = unlimited">
          <NumberInput value={doc.max_trades_per_day} min={1} step={1} allowBlank onChange={(v) => onChange({ max_trades_per_day: v })} />
        </Field>
        <Toggle checked={doc.session.trade_on_expiry_day ?? true} onChange={(v) => onChange({ session: { ...doc.session, trade_on_expiry_day: v } })} label="Trade on expiry day" />
      </Row>
    </Section>
  );
}
