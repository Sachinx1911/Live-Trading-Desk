"use client";

import { Columns3 } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ScanField } from "@/lib/api/generated";
import { cn } from "@/lib/utils";
import { COLUMN_SETS, COLUMN_SET_IDS } from "./lib";

/** 34px underline tabs (Overview / Performance / …) plus a column picker for "Custom". */
export function ColumnTabs({
  active,
  columns,
  fields,
  onSet,
  onColumns,
}: {
  active: string;
  columns: string[];
  fields: ScanField[];
  onSet: (id: string) => void;
  onColumns: (cols: string[]) => void;
}) {
  const groups = new Map<string, ScanField[]>();
  for (const f of fields) groups.set(f.group, [...(groups.get(f.group) ?? []), f]);
  const toggle = (name: string) => onColumns(columns.includes(name) ? columns.filter((c) => c !== name) : [...columns, name]);
  return (
    <div className="flex items-center gap-1 border-b border-border">
      {COLUMN_SET_IDS.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onSet(id)}
          className={cn(
            "-mb-px h-[34px] border-b-2 px-3 text-[13px] whitespace-nowrap transition-colors",
            active === id ? "border-accent font-semibold text-text-1" : "border-transparent text-text-2 hover:text-text-1",
          )}
        >
          {id === "custom" ? "Custom" : COLUMN_SETS[id].label}
        </button>
      ))}
      <Popover>
        <PopoverTrigger className="ml-auto inline-flex h-7 items-center gap-1 rounded-[var(--r-pill)] border border-border px-2.5 text-[12px] text-text-2 hover:bg-row-hover hover:text-text-1">
          <Columns3 className="size-3" /> Columns ({columns.length})
        </PopoverTrigger>
        <PopoverContent align="end" className="max-h-96 w-72 overflow-y-auto">
          {[...groups.entries()].map(([g, fs]) => (
            <div key={g} className="mb-2">
              <div className="mb-1 text-[11px] font-semibold tracking-wide text-text-3 uppercase">{g}</div>
              {fs.map((f) => (
                <label key={f.name} className="flex h-7 cursor-pointer items-center gap-2 rounded px-1 hover:bg-row-hover">
                  <input type="checkbox" checked={columns.includes(f.name)} onChange={() => toggle(f.name)} className="accent-[var(--accent)]" />
                  <span className="text-text-1">{f.label}</span>
                  {f.unit && <span className="text-[11px] text-text-3">{f.unit}</span>}
                </label>
              ))}
            </div>
          ))}
        </PopoverContent>
      </Popover>
    </div>
  );
}
