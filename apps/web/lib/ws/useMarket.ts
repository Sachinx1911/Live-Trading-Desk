"use client";

import { useEffect } from "react";
import type { Quote } from "@/lib/api/generated";
import { useQuotes } from "@/lib/api/queries";
import { marketSocket } from "./market";
import { quoteFreshness, useRealtimeStore } from "./store";

/**
 * Subscribe a set of instruments on the WebSocket and seed/refresh them from the REST poll.
 * The store keeps the newest message regardless of source.
 */
export function useMarketSubscription(ids: number[]) {
  const key = ids.join(",");
  useEffect(() => {
    if (!ids.length) return;
    return marketSocket.subscribe(ids);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const poll = useQuotes(ids);
  const putQuotes = useRealtimeStore((s) => s.putQuotes);
  useEffect(() => {
    if (poll.data) putQuotes(Object.values(poll.data.quotes));
  }, [poll.data, putQuotes]);
  return poll;
}

/** Quote + derived freshness, re-evaluated every second so ages tick honestly. */
export function useLiveQuote(id: number | null | undefined): { quote: Quote | undefined; freshness: ReturnType<typeof quoteFreshness> } {
  const quote = useRealtimeStore((s) => (id == null ? undefined : s.quotes[id]));
  const wsState = useRealtimeStore((s) => s.wsState);
  const tick = useRealtimeStore((s) => s.collectorSeenAt);
  void tick;
  return { quote, freshness: quoteFreshness(quote, wsState) };
}

export function num(v: string | number | null | undefined): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}
