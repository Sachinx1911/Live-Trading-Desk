"use client";

/**
 * Client-side realtime state. In Phase 1 nothing connects: every value starts as
 * "disconnected" and only a real backend message may change it. The WebSocket client is a
 * typed stub so pages can already subscribe to the shapes they will receive later.
 */
import { create } from "zustand";
import type { ConnectionState, Freshness } from "@/lib/api/generated";

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
  setWsState: (s: ConnectionState) => void;
  setSession: (s: MarketSessionStatus) => void;
  setProviderFreshness: (f: Freshness) => void;
  setBrokerSession: (b: RealtimeState["brokerSession"]) => void;
}

export const useRealtimeStore = create<RealtimeState>((set) => ({
  wsState: "disconnected",
  session: { exchange: "NSE", state: "unknown", asOf: null },
  providerFreshness: "disconnected",
  brokerSession: "none",
  setWsState: (wsState) => set({ wsState }),
  setSession: (session) => set({ session }),
  setProviderFreshness: (providerFreshness) => set({ providerFreshness }),
  setBrokerSession: (brokerSession) => set({ brokerSession }),
}));

/** Channel message shapes (mirrors docs/architecture/04-api-specification.md). */
export type WsMessage =
  | { channel: "market"; type: "quote"; payload: unknown }
  | { channel: "market"; type: "candle"; payload: unknown }
  | { channel: "orders"; type: "order_event"; payload: unknown }
  | { channel: "jobs"; type: "progress"; payload: unknown }
  | { channel: "system"; type: "session"; payload: MarketSessionStatus };

/** Stub: returns a no-op disconnect. Real connection lands in Phase 2. */
export function connectRealtime(): () => void {
  useRealtimeStore.getState().setWsState("disconnected");
  return () => {};
}
