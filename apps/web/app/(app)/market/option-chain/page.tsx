"use client";

import { useEffect, useState } from "react";
import { PanelCard } from "@/components/design";
import { OptionChainTable } from "@/components/market/OptionChainTable";
import { api } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { useChainExpiries } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

const UNDERLYINGS = ["NIFTY", "BANKNIFTY"];

export default function OptionChainPage() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [ids, setIds] = useState<Record<string, number>>({});
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  // Empty = latest snapshot; otherwise an IST date and time to look back to (Mark 1, 1.3).
  const [atDay, setAtDay] = useState("");
  const [atTime, setAtTime] = useState("");
  const at = atDay && atTime ? `${atDay}T${atTime}:00+05:30` : undefined;
  const id = ids[symbol] ?? null;
  const expiries = useChainExpiries(id);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const out: Record<string, number> = {};
      for (const sym of UNDERLYINGS) {
        try {
          const hits = await api<Instrument[]>(`/instruments?q=${sym}&exchange=NSE&limit=20`);
          const hit = hits.find((i) => i.symbol === sym && i.segment === "index") ?? hits.find((i) => i.symbol === sym);
          if (hit) out[sym] = hit.instrument_id;
        } catch {
          /* shown as unresolved */
        }
      }
      if (alive) setIds(out);
    })();
    return () => {
      alive = false;
    };
  }, []);

  // Fall back to the nearest known expiry without an extra render cycle.
  const effectiveExpiry = expiry && expiries.data?.includes(expiry) ? expiry : expiries.data?.[0];

  return (
    <div className="flex flex-col gap-3">
      <PanelCard bodyClassName="flex flex-wrap items-center gap-3 p-2">
        <div className="flex rounded-sm border border-border">
          {UNDERLYINGS.map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => {
                setSymbol(u);
                setExpiry(undefined);
              }}
              className={cn("px-3 py-1 text-xs font-medium", u === symbol ? "bg-raised text-accent" : "text-text-3 hover:text-text-2")}
            >
              {u}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-text-2">
          Expiry
          <select
            value={effectiveExpiry ?? ""}
            onChange={(e) => setExpiry(e.target.value || undefined)}
            className="h-7 border border-border bg-pane px-2 text-xs text-text-1"
            disabled={!expiries.data?.length}
          >
            {!expiries.data?.length && <option value="">No expiries known</option>}
            {expiries.data?.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-text-2">
          At
          <input type="date" value={atDay} onChange={(e) => setAtDay(e.target.value)} className="h-7 border border-border bg-pane px-2 text-xs text-text-1" />
          <input type="time" value={atTime} onChange={(e) => setAtTime(e.target.value)} className="h-7 border border-border bg-pane px-2 text-xs text-text-1" />
        </label>
        {at ? (
          <button
            type="button"
            onClick={() => {
              setAtDay("");
              setAtTime("");
            }}
            className="rounded-[var(--r-pill)] border border-border px-2 py-0.5 text-[11px] text-accent-text"
          >
            Back to latest
          </button>
        ) : (
          <span className="text-[11px] text-text-3">latest snapshot</span>
        )}
        {id == null && <span className="text-[11px] text-text-3">{symbol} not found in the instrument master yet.</span>}
      </PanelCard>
      <OptionChainTable underlyingId={id} expiry={effectiveExpiry ? `${effectiveExpiry}T15:30:00+05:30` : undefined} symbol={symbol} at={at} />
    </div>
  );
}
