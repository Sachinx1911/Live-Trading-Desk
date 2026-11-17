"use client";

/**
 * Client-side realtime state. Every value starts as "disconnected" and only a real
 * backend message may change it. Quotes arrive over /ws/market (see ./market.ts) or the
 * REST poll fallback; freshness is re-derived from the quote's own timestamp on read.
 */
import { create } from "zustand";
import type { CollectorDetail, ConnectionState, Freshness, Quote } from "@/lib/api/generated";

export type SessionState = "pre_open" | "open" | "post_close" | "closed" | "unknown";

export interface MarketSessionStatus {
  exchange: string;
  state: SessionState;
  /** ISO UTC of the last server message that set this state; null = never. */
  asOf: string | null;
}

export interface RealtimeState {
  wsState: ConnectionState;
  session: MarketSessionStatus;
  providerFreshness: Freshness;
  brokerSession: "none" | "valid" | "expired";
  collector: CollectorDetail | null;
  collectorSeenAt: string | null;
  quotes: Record<number, Quote>;
  subscribed: number[];
  setWsState: (s: ConnectionState) => void;
  setSession: (s: MarketSessionStatus) => void;
  setProviderFreshness: (f: Freshness) => void;
  setBrokerSession: (b: RealtimeState["brokerSession"]) => void;
  setCollector: (c: CollectorDetail | null) => void;
  putQuote: (q: Quote) => void;
  putQuotes: (qs: Quote[]) => void;
  setSubscribed: (ids: number[]) => void;
}

export const useRealtimeStore = create<RealtimeState>((set) => ({
  wsState: "disconnected",
  session: { exchange: "NSE", state: "unknown", asOf: null },
  providerFreshness: "disconnected",
  brokerSession: "none",
  collector: null,
  collectorSeenAt: null,
  quotes: {},
  subscribed: [],
  setWsState: (wsState) => set({ wsState }),
  setSession: (session) => set({ session }),
  setProviderFreshness: (providerFreshness) => set({ providerFreshness }),
  setBrokerSession: (brokerSession) => set({ brokerSession }),
  setCollector: (collector) =>
    set({
      collector,
      collectorSeenAt: new Date().toISOString(),
      session: deriveSession(collector),
      providerFreshness: collector
        ? collector.is_demo
          ? "demo"
          : collector.state === "connected"
            ? "live"
            : "disconnected"
        : "disconnected",
    }),
  putQuote: (q) =>
    set((s) => {
      const prev = s.quotes[q.instrument_id];
      // Never let an older message overwrite a newer one (REST poll vs WS race).
      if (prev && prev.ts > q.ts) return s;
      return { quotes: { ...s.quotes, [q.instrument_id]: q } };
    }),
  putQuotes: (qs) =>
    set((s) => {
      const next = { ...s.quotes };
      for (const q of qs) {
        const prev = next[q.instrument_id];
        if (!prev || prev.ts <= q.ts) next[q.instrument_id] = q;
      }
      return { quotes: next };
    }),
  setSubscribed: (subscribed) => set({ subscribed }),
}));

/** NSE session from the IST clock, only trusted while the collector reports a connected feed. */
function deriveSession(c: CollectorDetail | null): MarketSessionStatus {
  if (!c || c.state !== "connected") return { exchange: "NSE", state: "unknown", asOf: null };
  const now = new Date();
  const ist = new Date(now.getTime() + (330 + now.getTimezoneOffset()) * 60_000);
  const day = ist.getDay();
  const mins = ist.getHours() * 60 + ist.getMinutes();
  let state: SessionState = "closed";
  if (day >= 1 && day <= 5) {
    if (mins >= 9 * 60 && mins < 9 * 60 + 15) state = "pre_open";
    else if (mins >= 9 * 60 + 15 && mins < 15 * 60 + 30) state = "open";
    else if (mins >= 15 * 60 + 30 && mins < 16 * 60) state = "post_close";
  }
  return { exchange: "NSE", state, asOf: c.updated_at };
}

/** Client-side freshness from the quote's own timestamp (UI thresholds, page map §1.5). */
export function quoteFreshness(q: Quote | undefined, wsState: ConnectionState, now = Date.now()): Freshness {
  if (!q) return "disconnected";
  if (q.is_demo) return "demo";
  const age = (now - new Date(q.ts).getTime()) / 1000;
  if (age < 5 && wsState === "connected") return "live";
  if (age < 120) return "delayed";
  return "stale";
}

export function useQuote(id: number | null | undefined): Quote | undefined {
  return useRealtimeStore((s) => (id == null ? undefined : s.quotes[id]));
}

export function useWsState(): ConnectionState {
  return useRealtimeStore((s) => s.wsState);
}

/** Channel message shapes (mirrors docs/architecture/04-api-specification.md). */
export type WsMessage =
  | { channel: "market"; type: "quote"; payload: unknown }
  | { channel: "market"; type: "candle"; payload: unknown }
  | { channel: "orders"; type: "order_event"; payload: unknown }
  | { channel: "jobs"; type: "progress"; payload: unknown }
  | { channel: "system"; type: "session"; payload: MarketSessionStatus };

/** Connects the market WebSocket; returns a disconnect function for the shell's effect. */
export function connectRealtime(): () => void {
  // Lazy import keeps the store free of socket code on the server.
  let stop: (() => void) | null = null;
  let cancelled = false;
  void import("./market").then((m) => {
    if (cancelled) return;
    stop = m.marketSocket.start();
  });
  return () => {
    cancelled = true;
    stop?.();
  };
}
