"use client";

import { Plus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ScanCondition, ScanField, ScanFilters, ScanOp, ScanValue } from "@/lib/api/generated";
import { cn } from "@/lib/utils";
import { OP_LABEL, conditionLabel, defaultOp, opsForType } from "./lib";

type Group = "all" | "any";

const selectCls = "h-8 rounded-[var(--r-md)] border border-border bg-app px-2 text-[13px] text-text-1 outline-none focus:border-accent";

/** One condition editor: field picker (grouped), op by type, value widget by type. */
function ConditionEditor({ fields, initial, onDone, onCancel }: { fields: ScanField[]; initial?: ScanCondition; onDone: (c: ScanCondition) => void; onCancel: () => void }) {
  const byName = useMemo(() => new Map(fields.map((f) => [f.name, f])), [fields]);
  const [field, setField] = useState(initial?.field ?? fields[0]?.name ?? "");
  const f = byName.get(field);
  const [op, setOp] = useState<ScanOp>(initial?.op ?? (f ? defaultOp(f.type) : "eq"));
  const [value, setValue] = useState<ScanValue>(initial?.value ?? null);

  const groups = useMemo(() => {
    const m = new Map<string, ScanField[]>();
    for (const x of fields) m.set(x.group, [...(m.get(x.group) ?? []), x]);
    return [...m.entries()];
  }, [fields]);

  const pickField = (name: string) => {
    const nf = byName.get(name);
    setField(name);
    setOp(nf ? defaultOp(nf.type) : "eq");
    setValue(nf?.type === "bool" ? true : nf?.type === "enum" ? [] : null);
  };
  const pickOp = (o: ScanOp) => {
    setOp(o);
    if (o === "between") setValue([Number(Array.isArray(value) ? value[0] : value) || 0, Number(Array.isArray(value) ? value[1] : value) || 0]);
    else if (o === "in") setValue(Array.isArray(value) ? value : value == null ? [] : [value as string | number]);
    else if (Array.isArray(value)) setValue(value[0] ?? null);
  };

  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const valid = (() => {
    if (!f) return false;
    if (op === "between") return Array.isArray(value) && value.length === 2 && value.every((v) => typeof v === "number" && Number.isFinite(v));
    if (op === "in") return Array.isArray(value) && value.length > 0;
    if (f.type === "number" || f.type === "percent") return typeof value === "number" && Number.isFinite(value);
    return value != null && value !== "";
  })();

  let widget: React.ReactNode;
  if (!f) widget = null;
  else if (f.type === "bool") {
    widget = (
      <select className={selectCls} value={String(value)} onChange={(e) => setValue(e.target.value === "true")}>
        <option value="true">yes</option>
        <option value="false">no</option>
      </select>
    );
  } else if (f.type === "enum" && f.values) {
    const sel = Array.isArray(value) ? value.map(String) : value == null ? [] : [String(value)];
    const multi = op === "in";
    widget = (
      <div className="flex flex-wrap gap-1">
        {f.values.map((v) => {
          const on = sel.includes(v);
          return (
            <button
              key={v}
              type="button"
              onClick={() => (multi ? setValue(on ? sel.filter((x) => x !== v) : [...sel, v]) : setValue(v))}
              className={cn("h-7 rounded-[var(--r-pill)] border px-2.5 text-[12px]", on ? "border-transparent bg-raised font-semibold text-text-1" : "border-border text-text-2 hover:text-text-1")}
            >
              {v}
            </button>
          );
        })}
      </div>
    );
  } else if (op === "between") {
    const [a, b] = Array.isArray(value) ? value : [null, null];
    const t = f.type === "date" ? "date" : "number";
    widget = (
      <div className="flex items-center gap-2">
        <Input type={t} step="any" className="h-8 text-[13px] tabular" value={a ?? ""} onChange={(e) => setValue([t === "date" ? e.target.value : (num(e.target.value) as number), b as number])} />
        <span className="text-text-3">–</span>
        <Input type={t} step="any" className="h-8 text-[13px] tabular" value={b ?? ""} onChange={(e) => setValue([a as number, t === "date" ? e.target.value : (num(e.target.value) as number)])} />
      </div>
    );
  } else if (f.type === "number" || f.type === "percent") {
    widget = (
      <div className="flex items-center gap-2">
        <Input type="number" step="any" className="h-8 text-[13px] tabular" value={typeof value === "number" ? value : ""} onChange={(e) => setValue(num(e.target.value))} autoFocus />
        {f.unit && <span className="text-[12px] text-text-3">{f.unit}</span>}
      </div>
    );
  } else if (f.type === "date") {
    widget = <Input type="date" className="h-8 text-[13px]" value={typeof value === "string" ? value : ""} onChange={(e) => setValue(e.target.value || null)} />;
  } else {
    widget = (
      <Input
        className="h-8 text-[13px]"
        placeholder={op === "in" ? "comma separated" : "text"}
        value={Array.isArray(value) ? value.join(", ") : ((value as string | null) ?? "")}
        onChange={(e) => setValue(op === "in" ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean) : e.target.value)}
        autoFocus
      />
    );
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onDone({ field, op, value });
      }}
    >
      <select className={selectCls} value={field} onChange={(e) => pickField(e.target.value)}>
        {groups.map(([g, fs]) => (
          <optgroup key={g} label={g}>
            {fs.map((x) => (
              <option key={x.name} value={x.name}>{x.label}{x.unit ? ` (${x.unit})` : ""}</option>
            ))}
          </optgroup>
        ))}
      </select>
      {f?.description && <div className="text-[11px] text-text-3">{f.description}</div>}
      {f && (
        <select className={selectCls} value={op} onChange={(e) => pickOp(e.target.value as ScanOp)}>
          {opsForType(f.type).map((o) => (
            <option key={o} value={o}>{OP_LABEL[o]}</option>
          ))}
        </select>
      )}
      {widget}
      <div className="mt-1 flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" size="sm" disabled={!valid}>{initial ? "Update" : "Add"}</Button>
      </div>
    </form>
  );
}

function Chip({ c, field, onEdit, onRemove, fields }: { c: ScanCondition; field: ScanField | undefined; fields: ScanField[]; onEdit: (c: ScanCondition) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <span className="inline-flex h-[34px] items-center rounded-[var(--r-md)] border border-border bg-raised pl-3 text-[13px] whitespace-nowrap">
        <PopoverTrigger className="text-text-1 hover:text-accent">{conditionLabel(c, field)}</PopoverTrigger>
        <button type="button" onClick={onRemove} className="ml-1 inline-flex h-full items-center px-2 text-text-3 hover:text-down" aria-label="Remove filter">
          <X className="size-3.5" />
        </button>
      </span>
      <PopoverContent>
        <ConditionEditor fields={fields} initial={c} onDone={(nc) => { onEdit(nc); setOpen(false); }} onCancel={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}

function AddFilter({ fields, onAdd, label }: { fields: ScanField[]; onAdd: (c: ScanCondition) => void; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className="inline-flex h-[34px] items-center gap-1 rounded-[var(--r-md)] border border-dashed border-border px-3 text-[13px] text-text-2 hover:border-text-3 hover:text-text-1">
        <Plus className="size-3.5" /> {label}
      </PopoverTrigger>
      <PopoverContent>
        <ConditionEditor fields={fields} onDone={(c) => { onAdd(c); setOpen(false); }} onCancel={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}

/** Active filter chips (34px, radius 8 like TradingView) for the ALL group, plus an optional ANY-OF group. */
export function FilterChips({ fields, filters, onChange }: { fields: ScanField[]; filters: ScanFilters; onChange: (f: ScanFilters) => void }) {
  const byName = useMemo(() => new Map(fields.map((f) => [f.name, f])), [fields]);
  const [showAny, setShowAny] = useState(filters.any.length > 0);
  const set = (g: Group, list: ScanCondition[]) => onChange({ ...filters, [g]: list });
  const row = (g: Group) =>
    filters[g].map((c, i) => (
      <Chip
        key={`${g}-${i}-${c.field}`}
        c={c}
        field={byName.get(c.field)}
        fields={fields}
        onEdit={(nc) => set(g, filters[g].map((x, j) => (j === i ? nc : x)))}
        onRemove={() => set(g, filters[g].filter((_, j) => j !== i))}
      />
    ));
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold tracking-wide text-text-3 uppercase">All of</span>
        {row("all")}
        <AddFilter fields={fields} label="Add filter" onAdd={(c) => set("all", [...filters.all, c])} />
        {filters.all.length + filters.any.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => { onChange({ all: [], any: [] }); setShowAny(false); }}>Clear</Button>
        )}
        {!showAny && filters.any.length === 0 && (
          <button type="button" onClick={() => setShowAny(true)} className="text-[12px] text-text-3 hover:text-text-1">+ any-of group</button>
        )}
      </div>
      {(showAny || filters.any.length > 0) && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold tracking-wide text-text-3 uppercase">Any of</span>
          {row("any")}
          <AddFilter fields={fields} label="Add alternative" onAdd={(c) => set("any", [...filters.any, c])} />
          {filters.any.length === 0 && (
            <button type="button" onClick={() => setShowAny(false)} className="text-[12px] text-text-3 hover:text-text-1">remove group</button>
          )}
        </div>
      )}
    </div>
  );
}
