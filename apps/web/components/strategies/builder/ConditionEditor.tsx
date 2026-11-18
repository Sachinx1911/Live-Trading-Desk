"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DslCatalogue } from "@/lib/api/generated";
import { ARITH_OPS, OP_LABEL, SLOPE_DIRECTIONS } from "@/lib/dsl-catalogue-fallback";
import { conditionText, defaultCondition, defaultOperand, type Condition, type DslDoc, type IndicatorRef, type Operand } from "@/lib/dsl/types";
import { cn } from "@/lib/utils";
import { NumberInput, Select, TextInput, Toggle } from "./fields";

type Ctx = { doc: DslDoc; catalogue: DslCatalogue };

const KIND_LABEL: Record<string, string> = {
  compare: "Compare",
  cross: "Crossover",
  between: "Between",
  slope: "Slope",
  label: "Label equals",
  group: "Group (AND / OR)",
  not: "NOT",
};

const OPERAND_KINDS = ["indicator", "price", "const", "arith"] as const;

function outputsOf(ctx: Ctx, id: string): string[] {
  const spec = ctx.doc.indicators[id];
  const cat = spec ? ctx.catalogue.indicators.find((s) => s.type === spec.type) : undefined;
  return cat?.outputs ?? ["value"];
}

export function OperandEditor({ value, onChange, ctx, depth = 0 }: { value: Operand; onChange: (o: Operand) => void; ctx: Ctx; depth?: number }) {
  const ids = Object.keys(ctx.doc.indicators);
  const kindSel = (
    <Select
      value={value.kind}
      options={OPERAND_KINDS}
      labels={{ indicator: "Indicator", price: "Price", const: "Number", arith: "Formula" }}
      className="w-24"
      onChange={(k) => onChange(defaultOperand(k as Operand["kind"], ids))}
    />
  );
  switch (value.kind) {
    case "indicator": {
      const outs = outputsOf(ctx, value.id);
      return (
        <span className="inline-flex flex-wrap items-center gap-1">
          {kindSel}
          <Select value={value.id} allowBlank={ids.length ? "pick…" : "no indicators"} options={ids} className="w-28 font-mono" onChange={(id) => onChange({ ...value, id, field: outputsOf(ctx, id).includes(value.field ?? "value") ? value.field : outputsOf(ctx, id)[0] })} />
          {outs.length > 1 && <Select value={value.field ?? "value"} options={outs} className="w-24" onChange={(field) => onChange({ ...value, field })} />}
          <OffsetInput value={value.offset ?? 0} onChange={(offset) => onChange({ ...value, offset })} />
        </span>
      );
    }
    case "price":
      return (
        <span className="inline-flex flex-wrap items-center gap-1">
          {kindSel}
          <Select value={value.field} options={ctx.catalogue.price_fields} className="w-20" onChange={(field) => onChange({ ...value, field })} />
          <OffsetInput value={value.offset ?? 0} onChange={(offset) => onChange({ ...value, offset })} />
        </span>
      );
    case "const":
      return (
        <span className="inline-flex items-center gap-1">
          {kindSel}
          <NumberInput value={value.value} onChange={(v) => onChange({ ...value, value: v ?? 0 })} />
        </span>
      );
    case "arith":
      return (
        <span className={cn("inline-flex flex-wrap items-center gap-1 border border-dashed border-border px-1 py-0.5", depth > 2 && "border-down/60")}>
          {kindSel}
          <OperandEditor value={value.left} ctx={ctx} depth={depth + 1} onChange={(left) => onChange({ ...value, left })} />
          <Select value={value.op} options={ARITH_OPS} className="w-12" onChange={(op) => onChange({ ...value, op: op as "+" | "-" | "*" | "/" })} />
          <OperandEditor value={value.right} ctx={ctx} depth={depth + 1} onChange={(right) => onChange({ ...value, right })} />
        </span>
      );
  }
}

function OffsetInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <span className="inline-flex items-center gap-0.5 text-[10px] text-text-3" title="Bars back (0 = current closed bar)">
      ago
      <NumberInput value={value} min={0} max={100} step={1} className="w-12" onChange={(v) => onChange(Math.max(0, v ?? 0))} />
    </span>
  );
}

export function ConditionEditor({ value, onChange, onRemove, ctx, depth = 0 }: {
  value: Condition;
  onChange: (c: Condition) => void;
  onRemove?: () => void;
  ctx: Ctx;
  depth?: number;
}) {
  const ids = Object.keys(ctx.doc.indicators);
  const kindSel = (
    <Select
      value={value.kind}
      options={ctx.catalogue.condition_kinds}
      labels={KIND_LABEL}
      className="w-32"
      onChange={(k) => onChange(defaultCondition(k as Condition["kind"], ids))}
    />
  );
  const remove = onRemove ? <Button size="icon-xs" variant="ghost" aria-label="Remove condition" onClick={onRemove}><Trash2 /></Button> : null;

  if (value.kind === "group") {
    return (
      <div className={cn("flex flex-col gap-1.5 border-l-2 pl-2", value.op === "and" ? "border-accent/70" : "border-warn/70")}>
        <div className="flex flex-wrap items-center gap-1">
          {kindSel}
          <Select value={value.op} options={["and", "or"]} labels={{ and: "ALL of (AND)", or: "ANY of (OR)" }} className="w-28" onChange={(op) => onChange({ ...value, op: op as "and" | "or" })} />
          <Button size="xs" variant="ghost" disabled={value.conditions.length >= 10} onClick={() => onChange({ ...value, conditions: [...value.conditions, defaultCondition("compare", ids)] })}><Plus /> Condition</Button>
          <Button size="xs" variant="ghost" disabled={value.conditions.length >= 10 || depth >= 4} onClick={() => onChange({ ...value, conditions: [...value.conditions, defaultCondition("group", ids)] })}><Plus /> Sub-group</Button>
          {remove}
        </div>
        {value.conditions.length === 0 && <span className="text-[11px] text-down">Empty group — add at least one condition.</span>}
        {value.conditions.map((c, i) => (
          <ConditionEditor
            key={i}
            value={c}
            ctx={ctx}
            depth={depth + 1}
            onChange={(nc) => onChange({ ...value, conditions: value.conditions.map((x, j) => (j === i ? nc : x)) })}
            onRemove={() => onChange({ ...value, conditions: value.conditions.filter((_, j) => j !== i) })}
          />
        ))}
      </div>
    );
  }

  if (value.kind === "not") {
    return (
      <div className="flex flex-col gap-1.5 border-l-2 border-down/60 pl-2">
        <div className="flex items-center gap-1">{kindSel}{remove}</div>
        <ConditionEditor value={value.condition} ctx={ctx} depth={depth + 1} onChange={(condition) => onChange({ ...value, condition })} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-1">
        {kindSel}
        {value.kind === "compare" && (
          <>
            <OperandEditor value={value.left} ctx={ctx} onChange={(left) => onChange({ ...value, left })} />
            <Select value={value.op} options={ctx.catalogue.compare_ops} labels={OP_LABEL} className="w-14" onChange={(op) => onChange({ ...value, op })} />
            <OperandEditor value={value.right} ctx={ctx} onChange={(right) => onChange({ ...value, right })} />
          </>
        )}
        {value.kind === "cross" && (
          <>
            <OperandEditor value={value.left} ctx={ctx} onChange={(left) => onChange({ ...value, left })} />
            <Select value={value.direction} options={ctx.catalogue.cross_directions} labels={OP_LABEL} className="w-32" onChange={(direction) => onChange({ ...value, direction })} />
            <OperandEditor value={value.right} ctx={ctx} onChange={(right) => onChange({ ...value, right })} />
          </>
        )}
        {value.kind === "between" && (
          <>
            <OperandEditor value={value.value} ctx={ctx} onChange={(v) => onChange({ ...value, value: v })} />
            <span className="text-[11px] text-text-3">between</span>
            <OperandEditor value={value.low} ctx={ctx} onChange={(low) => onChange({ ...value, low })} />
            <span className="text-[11px] text-text-3">and</span>
            <OperandEditor value={value.high} ctx={ctx} onChange={(high) => onChange({ ...value, high })} />
          </>
        )}
        {value.kind === "slope" && (
          <>
            <OperandEditor value={value.value} ctx={ctx} onChange={(v) => onChange({ ...value, value: v })} />
            <Select value={value.direction} options={SLOPE_DIRECTIONS} className="w-20" onChange={(direction) => onChange({ ...value, direction: direction as "rising" | "falling" })} />
            <span className="text-[11px] text-text-3">for</span>
            <NumberInput value={value.bars} min={1} max={500} step={1} className="w-14" onChange={(bars) => onChange({ ...value, bars: Math.max(1, bars ?? 1) })} />
            <span className="text-[11px] text-text-3">bars</span>
            <Toggle checked={value.strict ?? false} onChange={(strict) => onChange({ ...value, strict })} label="strict" />
          </>
        )}
        {value.kind === "label" && (
          <>
            <OperandEditor value={value.value} ctx={ctx} onChange={(v) => onChange({ ...value, value: (v.kind === "indicator" ? v : { kind: "indicator", id: ids[0] ?? "", field: "label", offset: 0 }) as IndicatorRef })} />
            <span className="text-[11px] text-text-3">equals</span>
            <TextInput value={String(value.equals)} className="w-20" onChange={(equals) => onChange({ ...value, equals: equals !== "" && !Number.isNaN(Number(equals)) ? Number(equals) : equals })} />
          </>
        )}
        {remove}
      </div>
      <span className="pl-1 font-mono text-[10px] text-text-3">{conditionText(value)}</span>
    </div>
  );
}

/** One rule slot (e.g. entry.long): empty state with "Add", or the editor. */
export function RuleSlot({ title, value, onChange, ctx, hint }: { title: string; value: Condition | null | undefined; onChange: (c: Condition | null) => void; ctx: Ctx; hint?: string }) {
  const ids = Object.keys(ctx.doc.indicators);
  return (
    <div className="flex flex-col gap-1.5 border border-border bg-raised/40 p-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-text-1">{title}</span>
        {value ? (
          <Button size="xs" variant="ghost" onClick={() => onChange(null)}>Clear</Button>
        ) : (
          <div className="flex gap-1">
            <Button size="xs" variant="outline" onClick={() => onChange(defaultCondition("compare", ids))}><Plus /> Single</Button>
            <Button size="xs" variant="outline" onClick={() => onChange({ kind: "group", op: "and", conditions: [defaultCondition("compare", ids)] })}><Plus /> Group</Button>
          </div>
        )}
      </div>
      {value ? <ConditionEditor value={value} ctx={ctx} onChange={onChange} /> : <span className="text-[11px] text-text-3">{hint ?? "Not set."}</span>}
    </div>
  );
}
