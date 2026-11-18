"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const SECTIONS = ["universe", "session", "indicators", "entry", "exit", "stop_loss", "target", "trailing", "position_sizing", "regime_filter", "time_filters", "fill"];

function Section({ name, value }: { name: string; value: unknown }) {
  const [open, setOpen] = useState(name === "entry" || name === "indicators");
  return (
    <div className="border-b border-border/60 last:border-0">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-1 px-2 py-1 text-left text-[11px] font-semibold uppercase tracking-wide text-text-2 hover:text-text-1">
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />} {name}
        {value == null && <span className="ml-1 font-normal normal-case text-text-3">(not set)</span>}
      </button>
      {open && value != null && <pre className="overflow-x-auto px-3 pb-2 font-mono text-[11px] leading-snug text-text-1">{JSON.stringify(value, null, 2)}</pre>}
    </div>
  );
}

/** Read-only, collapsible rendering of a strategy DSL document. */
export function DslViewer({ dsl, className }: { dsl: Record<string, unknown>; className?: string }) {
  const rest = Object.fromEntries(Object.entries(dsl).filter(([k]) => !SECTIONS.includes(k)));
  return (
    <div className={cn("border border-border bg-raised", className)}>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-b border-border px-2 py-1.5 text-[11px] text-text-2">
        {["name", "timeframe", "market", "direction", "dsl_schema_version", "origin", "language"].map((k) =>
          dsl[k] != null ? (
            <span key={k}>
              <span className="text-text-3">{k}:</span> <span className="text-text-1">{String(dsl[k])}</span>
            </span>
          ) : null,
        )}
      </div>
      {SECTIONS.map((s) => (
        <Section key={s} name={s} value={dsl[s]} />
      ))}
      {Object.keys(rest).some((k) => !["name", "timeframe", "market", "direction", "dsl_schema_version", "origin", "language", "description", "original_text", "context_timeframes", "max_positions", "max_trades_per_day"].includes(k)) && (
        <Section name="other" value={rest} />
      )}
    </div>
  );
}
