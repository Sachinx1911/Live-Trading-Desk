"use client";

import type { DslCatalogue } from "@/lib/api/generated";
import type { DslDoc } from "@/lib/dsl/types";
import { RuleSlot } from "./ConditionEditor";
import { Field, NumberInput, Row, Section, Toggle } from "./fields";

export function RulesSection({ doc, onChange, catalogue }: { doc: DslDoc; onChange: (p: Partial<DslDoc>) => void; catalogue: DslCatalogue }) {
  const ctx = { doc, catalogue };
  const entry = doc.entry ?? { long: null, short: null, confirm_bars: 0, cooldown_bars: 0, one_entry_per_signal: true };
  const exit = doc.exit ?? { long: null, short: null, time_exit_bars: null, exit_on_opposite_signal: false };
  const setE = (p: Partial<typeof entry>) => onChange({ entry: { ...entry, ...p } });
  const setX = (p: Partial<typeof exit>) => onChange({ exit: { ...exit, ...p } });
  const showLong = doc.direction !== "short_only";
  const showShort = doc.direction !== "long_only";
  const noInd = Object.keys(doc.indicators).length === 0;

  return (
    <Section title="Conditions" subtitle="evaluated on closed bars; nest groups for AND / OR logic">
      {noInd && <span className="text-[11px] text-warn">Add indicators first — conditions can still use price and numbers.</span>}
      <div className="grid gap-2 md:grid-cols-2">
        {showLong && <RuleSlot title="Entry — long" value={entry.long} ctx={ctx} onChange={(c) => setE({ long: c })} hint="When to go long." />}
        {showShort && <RuleSlot title="Entry — short" value={entry.short} ctx={ctx} onChange={(c) => setE({ short: c })} hint="When to go short." />}
        {showLong && <RuleSlot title="Exit — long" value={exit.long} ctx={ctx} onChange={(c) => setX({ long: c })} hint="Optional signal exit; stop/target below still apply." />}
        {showShort && <RuleSlot title="Exit — short" value={exit.short} ctx={ctx} onChange={(c) => setX({ short: c })} hint="Optional signal exit; stop/target below still apply." />}
      </div>
      <Row>
        <Field label="Confirm bars" hint="signal must hold for N bars">
          <NumberInput value={entry.confirm_bars ?? 0} min={0} step={1} onChange={(v) => setE({ confirm_bars: v ?? 0 })} />
        </Field>
        <Field label="Cooldown bars" hint="after an exit">
          <NumberInput value={entry.cooldown_bars ?? 0} min={0} step={1} onChange={(v) => setE({ cooldown_bars: v ?? 0 })} />
        </Field>
        <Field label="Time exit bars" hint="blank = none">
          <NumberInput value={exit.time_exit_bars} min={1} step={1} allowBlank onChange={(v) => setX({ time_exit_bars: v })} />
        </Field>
        <Toggle checked={entry.one_entry_per_signal ?? true} onChange={(v) => setE({ one_entry_per_signal: v })} label="One entry per signal" />
        <Toggle checked={exit.exit_on_opposite_signal ?? false} onChange={(v) => setX({ exit_on_opposite_signal: v })} label="Exit on opposite signal" />
      </Row>
    </Section>
  );
}
