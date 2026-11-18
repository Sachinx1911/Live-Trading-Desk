"use client";

import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DslCatalogue } from "@/lib/api/generated";
import { TRAIL_MODES } from "@/lib/dsl-catalogue-fallback";
import type { DslDoc, LevelSpec, PartialTarget, TargetSpec, TrailingSpec } from "@/lib/dsl/types";
import { Field, NumberInput, Row, Section, Select, Toggle } from "./fields";

const UNIT_LABEL: Record<string, string> = { points: "Points", percent: "Percent", atr: "× ATR", structure: "Structure level", indicator: "Indicator value" };

function LevelFields({ level, onChange, doc, catalogue, allowRR, rr, onRR }: {
  level: LevelSpec | TargetSpec;
  onChange: (p: Partial<LevelSpec>) => void;
  doc: DslDoc;
  catalogue: DslCatalogue;
  allowRR?: boolean;
  rr?: number | null;
  onRR?: (v: number | null) => void;
}) {
  const ids = Object.keys(doc.indicators);
  const atrIds = ids.filter((i) => doc.indicators[i].type === "ATR");
  const unit = level.unit ?? "";
  const options = allowRR ? ["rr", ...catalogue.level_units] : catalogue.level_units;
  const labels = { ...UNIT_LABEL, rr: "Risk : reward multiple" };
  const indRef = level.indicator_ref ?? { kind: "indicator" as const, id: ids[0] ?? "", field: "value", offset: 0 };
  return (
    <>
      <Field label="Unit">
        <Select value={allowRR && !unit ? "rr" : unit} options={options} labels={labels} className="w-40" onChange={(v) => (v === "rr" ? onChange({ unit: null as unknown as string }) : onChange({ unit: v }))} />
      </Field>
      {allowRR && !unit && (
        <Field label="R : R">
          <NumberInput value={rr} min={0.1} step={0.1} placeholder="2" onChange={(v) => onRR?.(v)} />
        </Field>
      )}
      {(unit === "points" || unit === "percent" || unit === "atr") && (
        <Field label={unit === "atr" ? "Multiplier" : "Value"}>
          <NumberInput value={level.value} min={0} onChange={(v) => onChange({ value: v })} />
        </Field>
      )}
      {unit === "atr" && (
        <Field label="ATR indicator">
          <Select value={level.atr_indicator_id} allowBlank={atrIds.length ? "pick…" : "add an ATR first"} options={atrIds} className="w-28 font-mono" onChange={(v) => onChange({ atr_indicator_id: v || null })} />
        </Field>
      )}
      {unit === "structure" && (
        <>
          <Field label="Level">
            <Select value={level.structure} allowBlank="pick…" options={catalogue.structure_levels} onChange={(v) => onChange({ structure: v || null })} />
          </Field>
          <Field label="From indicator" hint="optional SWING / PREV_DAY / OPENING_RANGE id">
            <Select value={level.structure_indicator_id} allowBlank="auto" options={ids} className="w-28 font-mono" onChange={(v) => onChange({ structure_indicator_id: v || null })} />
          </Field>
        </>
      )}
      {unit === "indicator" && (
        <Field label="Indicator">
          <Select value={indRef.id} allowBlank="pick…" options={ids} className="w-28 font-mono" onChange={(v) => onChange({ indicator_ref: { ...indRef, id: v } })} />
        </Field>
      )}
      {(unit === "structure" || unit === "indicator") && (
        <Field label="Buffer points">
          <NumberInput value={level.buffer_points ?? 0} onChange={(v) => onChange({ buffer_points: v ?? 0 })} />
        </Field>
      )}
    </>
  );
}

export function RiskSection({ doc, onChange, catalogue }: { doc: DslDoc; onChange: (p: Partial<DslDoc>) => void; catalogue: DslCatalogue }) {
  const ids = Object.keys(doc.indicators);
  const atrIds = ids.filter((i) => doc.indicators[i].type === "ATR");
  const sl = doc.stop_loss;
  const tg = doc.target;
  const tr = doc.trailing;
  const ps = doc.position_sizing ?? { method: "fixed_lots", lots: 1, max_lots: 1 };
  const setPS = (p: Partial<typeof ps>) => onChange({ position_sizing: { ...ps, ...p } });
  const setTG = (p: Partial<TargetSpec>) => onChange({ target: { ...(tg ?? { unit: "percent", value: 1, partial: [] }), ...p } });
  const setTR = (p: Partial<TrailingSpec>) => onChange({ trailing: { ...(tr ?? { mode: "percent", value: 0.5 }), ...p } });
  const partials = tg?.partial ?? [];
  const setPartial = (i: number, p: Partial<PartialTarget>) => setTG({ partial: partials.map((x, j) => (j === i ? { ...x, ...p } : x)) });

  return (
    <Section title="Risk & execution" subtitle="stop, target, trailing, sizing, order types">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Toggle checked={!!sl} onChange={(v) => onChange({ stop_loss: v ? { unit: "percent", value: 0.5, buffer_points: 0 } : null })} label="Stop loss" />
          {!sl && <span className="text-[11px] text-warn">No stop loss — the risk engine will reject this for paper/live.</span>}
        </div>
        {sl && <Row><LevelFields level={sl} doc={doc} catalogue={catalogue} onChange={(p) => onChange({ stop_loss: { ...sl, ...p } })} /></Row>}
      </div>

      <div className="flex flex-col gap-1">
        <Toggle checked={!!tg} onChange={(v) => onChange({ target: v ? { unit: "percent", value: 1, buffer_points: 0, partial: [] } : null })} label="Target" />
        {tg && (
          <>
            <Row>
              <LevelFields level={tg} doc={doc} catalogue={catalogue} allowRR rr={tg.rr_multiple} onRR={(v) => setTG({ rr_multiple: v })} onChange={(p) => setTG(p as Partial<TargetSpec>)} />
            </Row>
            <div className="flex items-center justify-between pt-1">
              <span className="text-[10px] uppercase tracking-wide text-text-3">Partial targets</span>
              <Button size="xs" variant="ghost" onClick={() => setTG({ partial: [...partials, { at: { unit: "percent", value: 0.5, buffer_points: 0 }, close_pct: 50, move_stop_to_breakeven: true }] })}><Plus /> Add partial</Button>
            </div>
            {partials.map((p, i) => (
              <Row key={i} className="border-l-2 border-border pl-2">
                <LevelFields level={p.at} doc={doc} catalogue={catalogue} onChange={(x) => setPartial(i, { at: { ...p.at, ...x } })} />
                <Field label="Close %">
                  <NumberInput value={p.close_pct} min={1} max={100} onChange={(v) => setPartial(i, { close_pct: v ?? 50 })} />
                </Field>
                <Toggle checked={p.move_stop_to_breakeven ?? false} onChange={(v) => setPartial(i, { move_stop_to_breakeven: v })} label="Move stop to breakeven" />
                <Button size="icon-xs" variant="ghost" aria-label="Remove partial target" onClick={() => setTG({ partial: partials.filter((_, j) => j !== i) })}><X /></Button>
              </Row>
            ))}
          </>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <Toggle checked={!!tr} onChange={(v) => onChange({ trailing: v ? { mode: "percent", value: 0.5 } : null })} label="Trailing stop" />
        {tr && (
          <Row>
            <Field label="Mode">
              <Select value={tr.mode} options={TRAIL_MODES} onChange={(v) => setTR({ mode: v })} />
            </Field>
            {(tr.mode === "atr" || tr.mode === "percent" || tr.mode === "points") && (
              <Field label={tr.mode === "atr" ? "Multiplier" : "Value"}>
                <NumberInput value={tr.value} min={0} onChange={(v) => setTR({ value: v })} />
              </Field>
            )}
            {tr.mode === "atr" && (
              <Field label="ATR indicator">
                <Select value={tr.atr_indicator_id} allowBlank={atrIds.length ? "pick…" : "add an ATR first"} options={atrIds} className="w-28 font-mono" onChange={(v) => setTR({ atr_indicator_id: v || null })} />
              </Field>
            )}
            {tr.mode === "indicator" && (
              <Field label="Indicator">
                <Select value={tr.indicator_ref?.id} allowBlank="pick…" options={ids} className="w-28 font-mono" onChange={(v) => setTR({ indicator_ref: { kind: "indicator", id: v, field: "value", offset: 0 } })} />
              </Field>
            )}
            <Field label="Activate after (points)" hint="blank = immediately">
              <NumberInput value={tr.activate_after?.value} allowBlank min={0} onChange={(v) => setTR({ activate_after: v == null ? null : { unit: "points", value: v, buffer_points: 0 } })} />
            </Field>
          </Row>
        )}
      </div>

      <Row>
        <Field label="Position sizing">
          <Select value={ps.method} options={catalogue.sizing_methods} labels={{ fixed_lots: "Fixed lots", fixed_quantity: "Fixed quantity", fixed_capital: "Fixed capital (₹)", risk_percent: "Risk % of equity" }} className="w-40" onChange={(method) => setPS({ method, lots: method === "fixed_lots" ? (ps.lots ?? 1) : null, quantity: method === "fixed_quantity" ? (ps.quantity ?? 1) : null, capital: method === "fixed_capital" ? (ps.capital ?? 100000) : null, risk_percent: method === "risk_percent" ? (ps.risk_percent ?? 1) : null })} />
        </Field>
        {ps.method === "fixed_lots" && <Field label="Lots"><NumberInput value={ps.lots} min={1} step={1} onChange={(v) => setPS({ lots: v })} /></Field>}
        {ps.method === "fixed_quantity" && <Field label="Quantity"><NumberInput value={ps.quantity} min={1} step={1} onChange={(v) => setPS({ quantity: v })} /></Field>}
        {ps.method === "fixed_capital" && <Field label="Capital ₹"><NumberInput value={ps.capital} min={1} className="w-28" onChange={(v) => setPS({ capital: v })} /></Field>}
        {ps.method === "risk_percent" && <Field label="Risk % per trade"><NumberInput value={ps.risk_percent} min={0.01} max={100} onChange={(v) => setPS({ risk_percent: v })} /></Field>}
        <Field label="Max lots" hint="blank = risk engine cap"><NumberInput value={ps.max_lots} min={1} step={1} allowBlank onChange={(v) => setPS({ max_lots: v })} /></Field>
        <Field label="Max capital %" hint="blank = risk engine cap"><NumberInput value={ps.max_capital_pct} min={1} max={100} allowBlank onChange={(v) => setPS({ max_capital_pct: v })} /></Field>
      </Row>

      <Row>
        <Field label="Entry order">
          <Select value={doc.fill.entry_order_type} options={["MARKET", "LIMIT_AT_CLOSE", "LIMIT_OFFSET"]} labels={{ MARKET: "Market", LIMIT_AT_CLOSE: "Limit at close", LIMIT_OFFSET: "Limit with offset" }} className="w-36" onChange={(v) => onChange({ fill: { ...doc.fill, entry_order_type: v } })} />
        </Field>
        {doc.fill.entry_order_type === "LIMIT_OFFSET" && (
          <Field label="Offset points"><NumberInput value={doc.fill.limit_offset_points ?? 0} onChange={(v) => onChange({ fill: { ...doc.fill, limit_offset_points: v ?? 0 } })} /></Field>
        )}
        {doc.fill.entry_order_type !== "MARKET" && (
          <Field label="Limit timeout bars"><NumberInput value={doc.fill.limit_timeout_bars ?? 1} min={1} step={1} onChange={(v) => onChange({ fill: { ...doc.fill, limit_timeout_bars: v ?? 1 } })} /></Field>
        )}
        <Field label="Stop order">
          <Select value={doc.fill.stop_order_type} options={["SL_MARKET", "SL_LIMIT"]} labels={{ SL_MARKET: "SL-Market", SL_LIMIT: "SL-Limit" }} className="w-28" onChange={(v) => onChange({ fill: { ...doc.fill, stop_order_type: v } })} />
        </Field>
      </Row>
    </Section>
  );
}
