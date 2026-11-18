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

/* Search field + glass result list; rows 40px: ticker 600 + name muted + segment tag (§6a). */
export function InstrumentSearch({
  onPick,
  placeholder = "Add instrument…",
  autoFocus = false,
}: {
  onPick: (i: Instrument) => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState("");
  const { data, isFetching } = useInstrumentSearch(q, "NSE", 12);
  return (
    <div className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-text-3" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          className="h-7 rounded-[var(--r-pill)] bg-raised pl-8 text-[13px]"
          aria-label="Search instruments"
          autoFocus={autoFocus}
        />
      </div>
      {q.trim() && (
        <ul className="glass absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-[var(--r-md)] py-1">
          {isFetching && !data && <li className="px-3 py-2 text-[12px] text-text-3">Searching…</li>}
          {data && data.length === 0 && <li className="px-3 py-2 text-[12px] text-text-3">No match</li>}
          {data?.map((i) => (
            <li key={i.instrument_id}>
              <button
                type="button"
                onClick={() => {
                  onPick(i);
                  setQ("");
                }}
                className="flex h-10 w-full items-center justify-between gap-3 px-3 text-left hover:bg-raised"
              >
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-semibold text-text-1">{instrumentLabel(i)}</span>
                  <span className="block truncate text-[12px] text-text-3">{i.name}</span>
                </span>
                <span className="shrink-0 rounded-full bg-app px-2 text-[10px] uppercase text-text-3">{i.segment}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
