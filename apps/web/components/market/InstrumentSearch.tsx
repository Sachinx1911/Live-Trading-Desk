"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import type { Instrument } from "@/lib/api/generated";
import { useInstrumentSearch } from "@/lib/api/queries";

export function instrumentLabel(i: Instrument): string {
  if (i.segment === "options" && i.strike) return `${i.underlying_symbol ?? i.symbol} ${Number(i.strike)} ${i.option_type} ${i.expiry ?? ""}`;
  if (i.segment === "futures") return `${i.underlying_symbol ?? i.symbol} FUT ${i.expiry ?? ""}`;
  return i.symbol;
}

export function InstrumentSearch({ onPick, placeholder = "Add instrument…" }: { onPick: (i: Instrument) => void; placeholder?: string }) {
  const [q, setQ] = useState("");
  const { data, isFetching } = useInstrumentSearch(q, "NSE", 12);
  return (
    <div className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute top-2 left-2 size-3.5 text-text-muted" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="h-8 pl-7 text-xs" aria-label="Search instruments" />
      </div>
      {q.trim() && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-border-subtle bg-panel-raised shadow-lg">
          {isFetching && !data && <li className="px-2 py-1.5 text-[11px] text-text-muted">Searching…</li>}
          {data && data.length === 0 && <li className="px-2 py-1.5 text-[11px] text-text-muted">No match</li>}
          {data?.map((i) => (
            <li key={i.instrument_id}>
              <button
                type="button"
                onClick={() => {
                  onPick(i);
                  setQ("");
                }}
                className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-xs hover:bg-panel"
              >
                <span className="truncate text-text-primary">{instrumentLabel(i)}</span>
                <span className="shrink-0 text-[10px] uppercase text-text-muted">{i.segment}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
