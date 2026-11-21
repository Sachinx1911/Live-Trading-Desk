"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { OpenAsPanel } from "@/components/panels/OpenAsPanel";
import { DataStateBadge, Dash, PanelCard, Pct } from "@/components/design";
import { api } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { formatNumber } from "@/lib/format";
import { MAX_QUOTE_SYMBOLS } from "@/lib/panels";
import { cn } from "@/lib/utils";
import { num, useLiveQuote, useMarketSubscription } from "@/lib/ws/useMarket";
import { InstrumentSearch, instrumentLabel } from "./InstrumentSearch";

const STORAGE_KEY = "tp.watchlist";
const DEFAULT_SYMBOLS = ["NIFTY", "BANKNIFTY", "INDIAVIX"];

export type WatchItem = Pick<Instrument, "instrument_id" | "symbol" | "segment" | "name"> & { label: string };

function load(): WatchItem[] | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as WatchItem[]) : null;
  } catch {
    return null;
  }
}

function save(items: WatchItem[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

async function resolveDefaults(): Promise<WatchItem[]> {
  const out: WatchItem[] = [];
  for (const sym of DEFAULT_SYMBOLS) {
    try {
      const hits = await api<Instrument[]>(`/instruments?q=${encodeURIComponent(sym)}&exchange=NSE&limit=20`);
      const hit = hits.find((i) => i.symbol === sym && i.segment === "index") ?? hits.find((i) => i.symbol === sym);
      if (hit) out.push({ instrument_id: hit.instrument_id, symbol: hit.symbol, segment: hit.segment, name: hit.name, label: instrumentLabel(hit) });
    } catch {
      /* API down: the list stays empty and the UI says so */
    }
  }
  return out;
}

/** Persisted watchlist; defaults resolved from the API on first use. */
export function useWatchlist() {
  const [items, setItems] = useState<WatchItem[] | null>(null);
  useEffect(() => {
    let alive = true;
    // Async on purpose: localStorage is read after hydration, defaults come from the API.
    void (async () => {
      const stored = load();
      const d = stored ?? (await resolveDefaults());
      if (!alive) return;
      setItems(d);
      if (!stored && d.length) save(d);
    })();
    return () => {
      alive = false;
    };
  }, []);
  const add = (i: Instrument) =>
    setItems((cur) => {
      const list = cur ?? [];
      if (list.some((x) => x.instrument_id === i.instrument_id)) return list;
      const next = [...list, { instrument_id: i.instrument_id, symbol: i.symbol, segment: i.segment, name: i.name, label: instrumentLabel(i) }];
      save(next);
      return next;
    });
  const remove = (id: number) =>
    setItems((cur) => {
      const next = (cur ?? []).filter((x) => x.instrument_id !== id);
      save(next);
      return next;
    });
  return { items, add, remove };
}

function Row({ item, selected, onSelect, onRemove }: { item: WatchItem; selected: boolean; onSelect: () => void; onRemove: () => void }) {
  const { quote, freshness } = useLiveQuote(item.instrument_id);
  const ltp = num(quote?.ltp);
  const prev = num(quote?.prev_close);
  const chg = ltp != null && prev ? ((ltp - prev) / prev) * 100 : null;
  return (
    <li
      className={cn(
        "group flex h-[var(--h-row-dense)] cursor-pointer items-center gap-2 border-b border-border-row px-3 last:border-0 hover:bg-row-hover",
        selected && "bg-raised",
        quote?.is_demo && "demo-stripes",
      )}
      onClick={onSelect}
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] leading-4 font-semibold text-text-1">{item.label}</p>
        <p className="truncate text-[11px] leading-3 text-text-3">{item.name ?? item.segment}</p>
      </div>
      <div className="flex flex-col items-end">
        {ltp == null ? (
          <Dash className="text-sm" />
        ) : (
          <span className={cn("tabular text-[14px] leading-4 text-text-1", freshness === "stale" && "text-text-2")}>
            {item.segment === "index" ? formatNumber(ltp, 2) : `₹${formatNumber(ltp, 2)}`}
          </span>
        )}
        <Pct value={chg} className="text-[12px] leading-3" />
      </div>
      <DataStateBadge state={freshness} className="shrink-0" />
      <button
        type="button"
        aria-label={`Remove ${item.symbol}`}
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        className="invisible text-text-3 hover:text-text-1 group-hover:visible"
      >
        <X className="size-3.5" />
      </button>
    </li>
  );
}

export function Watchlist({ selectedId, onSelect, className }: { selectedId: number | null; onSelect: (item: WatchItem) => void; className?: string }) {
  const { items, add, remove } = useWatchlist();
  const ids = (items ?? []).map((i) => i.instrument_id);
  useMarketSubscription(ids);
  useEffect(() => {
    if (selectedId == null && items && items.length) onSelect(items[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);
  return (
    <PanelCard
      title="Watchlist"
      actions={items?.length ? <OpenAsPanel panel="quotes" params={{ symbols: items.slice(0, MAX_QUOTE_SYMBOLS).map((i) => i.symbol).join(",") }} /> : undefined}
      className={className}
      bodyClassName="flex flex-col gap-2 p-0 pt-2 [&>div:first-child]:px-3">
      <InstrumentSearch onPick={add} />
      {items === null ? (
        <p className="px-2 text-[11px] text-text-3">Resolving instruments…</p>
      ) : items.length === 0 ? (
        <p className="px-2 text-[11px] text-text-3">No instruments. Search above, or run the collector to sync the instrument master.</p>
      ) : (
        <ul className="flex flex-col">
          {items.map((it) => (
            <Row key={it.instrument_id} item={it} selected={it.instrument_id === selectedId} onSelect={() => onSelect(it)} onRemove={() => remove(it.instrument_id)} />
          ))}
        </ul>
      )}
    </PanelCard>
  );
}
