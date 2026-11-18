"use client";

import { Plus, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { DslCatalogue, DslIndicatorSpec, DslParamSpec } from "@/lib/api/generated";
import type { DslDoc, IndicatorSpec } from "@/lib/dsl/types";
import { Field, NumberInput, Row, Section, Select, TextInput } from "./fields";

function defaultId(type: string, spec: DslIndicatorSpec | undefined, taken: string[]): string {
  const p = spec?.params.find((x) => x.type === "int");
  const base = `${type.toLowerCase()}${p && typeof p.default === "number" ? p.default : ""}`;
  let id = base;
  let n = 2;
  while (taken.includes(id)) id = `${base}_${n++}`;
  return id;
}

export function IndicatorsSection({ doc, onChange, catalogue }: { doc: DslDoc; onChange: (p: Partial<DslDoc>) => void; catalogue: DslCatalogue }) {
  const [newType, setNewType] = useState(catalogue.indicators[0]?.type ?? "EMA");
  const entries = Object.entries(doc.indicators);
  const specOf = (t: string) => catalogue.indicators.find((s) => s.type === t);
  const timeframes = [doc.timeframe, ...doc.context_timeframes];

  const update = (id: string, patch: Partial<IndicatorSpec>) => onChange({ indicators: { ...doc.indicators, [id]: { ...doc.indicators[id], ...patch } } });
  const rename = (oldId: string, newId: string) => {
    if (!newId || newId === oldId || newId in doc.indicators) return;
    const next: Record<string, IndicatorSpec> = {};
    for (const [k, v] of entries) next[k === oldId ? newId : k] = v;
    onChange({ indicators: next });
  };
  const remove = (id: string) => {
    const next = { ...doc.indicators };
    delete next[id];
    onChange({ indicators: next });
  };
  const add = () => {
    const spec = specOf(newType);
    const params: Record<string, number | string> = {};
    for (const p of spec?.params ?? []) if (p.default != null) params[p.name] = p.default;
    const id = defaultId(newType, spec, Object.keys(doc.indicators));
    onChange({ indicators: { ...doc.indicators, [id]: { type: newType, params, source: "close", timeframe: null } } });
  };

  return (
    <Section
      title="Indicators"
      subtitle={`${entries.length} defined`}
      actions={
        <div className="flex items-center gap-1">
          <Select value={newType} options={catalogue.indicators.map((s) => s.type)} labels={Object.fromEntries(catalogue.indicators.map((s) => [s.type, s.label]))} onChange={setNewType} className="w-56" />
          <Button size="xs" variant="outline" onClick={add}><Plus /> Add</Button>
        </div>
      }
    >
      {entries.length === 0 && <span className="text-[11px] text-text-3">No indicators yet. Add one, then reference it in the conditions below.</span>}
      {entries.map(([id, spec]) => {
        const cat = specOf(spec.type);
        return (
          <Row key={id} className="items-end border-b border-border/60 pb-2 last:border-b-0 last:pb-0">
            <Field label="Id">
              <IdInput value={id} onCommit={(v) => rename(id, v)} />
            </Field>
            <Field label="Type">
              <span className="inline-flex h-7 items-center text-[11px] text-text-1">{spec.type}</span>
            </Field>
            {(cat?.params ?? Object.keys(spec.params).map((n): DslParamSpec => ({ name: n, type: "float" }))).map((p) => (
              <Field key={p.name} label={p.name}>
                {p.type === "enum" ? (
                  <Select value={String(spec.params[p.name] ?? p.default ?? "")} options={p.options ?? []} onChange={(v) => update(id, { params: { ...spec.params, [p.name]: v } })} />
                ) : p.type === "string" ? (
                  <TextInput value={String(spec.params[p.name] ?? "")} className="w-24" onChange={(v) => update(id, { params: { ...spec.params, [p.name]: v } })} />
                ) : (
                  <NumberInput
                    value={typeof spec.params[p.name] === "number" ? (spec.params[p.name] as number) : null}
                    min={p.min ?? undefined}
                    max={p.max ?? undefined}
                    step={p.type === "int" ? 1 : "any"}
                    onChange={(v) => update(id, { params: { ...spec.params, [p.name]: v ?? 0 } })}
                  />
                )}
              </Field>
            ))}
            <Field label="Source">
              <Select value={spec.source ?? "close"} options={catalogue.price_fields} onChange={(v) => update(id, { source: v })} />
            </Field>
            <Field label="Timeframe">
              <Select value={spec.timeframe ?? ""} allowBlank={`strategy (${doc.timeframe})`} options={timeframes.filter((t, i) => i > 0)} onChange={(v) => update(id, { timeframe: v || null })} />
            </Field>
            <span className="pb-1.5 text-[10px] text-text-3">outputs: {(cat?.outputs ?? ["value"]).join(", ")}</span>
            <Button size="icon-xs" variant="ghost" className="mb-0.5" aria-label={`Remove ${id}`} onClick={() => remove(id)}><X /></Button>
          </Row>
        );
      })}
    </Section>
  );
}

function IdInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [v, setV] = useState(value);
  return (
    <input
      type="text"
      value={v}
      onChange={(e) => setV(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
      onBlur={() => onCommit(v)}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      className="h-7 w-28 border border-border bg-raised px-1.5 font-mono text-[11px] text-text-1 outline-none focus:border-accent"
    />
  );
}
