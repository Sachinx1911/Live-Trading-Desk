"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ImportMapping, Timeframe } from "@/lib/api/generated";
import { IMPORT_TIMEFRAMES } from "./importMapping";

const SEL = "h-8 w-full border border-border bg-raised px-2 text-xs";
const INPUT = "h-8 text-xs";

function ColumnField({
  id,
  label,
  value,
  columns,
  optional,
  onChange,
}: {
  id: string;
  label: string;
  value: string | null | undefined;
  columns: string[];
  optional?: boolean;
  onChange: (v: string) => void;
}) {
  // With a known header we offer a select; otherwise (Parquet/JSON/Excel) a free text field.
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        {optional && <span className="ml-1 text-text-3">(optional)</span>}
      </Label>
      {columns.length > 0 ? (
        <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className={SEL}>
          <option value="">{optional ? "— none —" : "— choose —"}</option>
          {columns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      ) : (
        <Input id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value)} className={INPUT} placeholder={optional ? "none" : label.toLowerCase()} />
      )}
    </div>
  );
}

export function ImportMappingForm({
  mapping,
  columns,
  disabled,
  onChange,
}: {
  mapping: ImportMapping;
  columns: string[];
  disabled?: boolean;
  onChange: (m: ImportMapping) => void;
}) {
  const set = <K extends keyof ImportMapping>(k: K, v: ImportMapping[K]) => onChange({ ...mapping, [k]: v });
  const usingSymbolColumn = !!mapping.symbol_column;
  return (
    <fieldset disabled={disabled} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="im-exchange">Exchange</Label>
        <Input id="im-exchange" value={mapping.exchange} onChange={(e) => set("exchange", e.target.value.toUpperCase())} className={INPUT} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="im-tf">Timeframe</Label>
        <select id="im-tf" value={mapping.timeframe} onChange={(e) => set("timeframe", e.target.value as Timeframe)} className={SEL}>
          {IMPORT_TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="im-symbol">Symbol {usingSymbolColumn && <span className="ml-1 text-text-3">(from column)</span>}</Label>
        <Input
          id="im-symbol"
          value={mapping.symbol ?? ""}
          onChange={(e) => set("symbol", e.target.value.toUpperCase())}
          disabled={usingSymbolColumn}
          placeholder="RELIANCE"
          className={INPUT}
        />
      </div>
      <ColumnField id="im-symcol" label="Symbol column" value={mapping.symbol_column} columns={columns} optional onChange={(v) => set("symbol_column", v || null)} />

      <ColumnField id="im-ts" label="Timestamp column" value={mapping.ts_column} columns={columns} onChange={(v) => set("ts_column", v)} />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="im-tsfmt">
          Timestamp format <span className="ml-1 text-text-3">(optional)</span>
        </Label>
        <Input id="im-tsfmt" value={mapping.ts_format ?? ""} onChange={(e) => set("ts_format", e.target.value || null)} placeholder="auto: ISO / epoch" className={INPUT} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="im-tz">Timezone of naive timestamps</Label>
        <Input id="im-tz" value={mapping.timezone} onChange={(e) => set("timezone", e.target.value)} className={INPUT} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="im-label">
          Source label <span className="ml-1 text-text-3">(optional)</span>
        </Label>
        <Input id="im-label" value={mapping.source_label ?? ""} onChange={(e) => set("source_label", e.target.value || null)} placeholder="e.g. vendor export 2024" className={INPUT} />
      </div>

      <ColumnField id="im-open" label="Open" value={mapping.open_column} columns={columns} onChange={(v) => set("open_column", v)} />
      <ColumnField id="im-high" label="High" value={mapping.high_column} columns={columns} onChange={(v) => set("high_column", v)} />
      <ColumnField id="im-low" label="Low" value={mapping.low_column} columns={columns} onChange={(v) => set("low_column", v)} />
      <ColumnField id="im-close" label="Close" value={mapping.close_column} columns={columns} onChange={(v) => set("close_column", v)} />
      <ColumnField id="im-vol" label="Volume" value={mapping.volume_column} columns={columns} optional onChange={(v) => set("volume_column", v || null)} />
      <ColumnField id="im-oi" label="Open interest" value={mapping.oi_column} columns={columns} optional onChange={(v) => set("oi_column", v || null)} />
    </fieldset>
  );
}
