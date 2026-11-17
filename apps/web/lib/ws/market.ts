"use client";

/**
 * Singleton client for /ws/market. Frames are binary JSON. Reconnects with backoff,
 * resubscribes, and feeds the Zustand store. Nothing is invented on this side: when the
 * socket is down the store's wsState says so and every freshness degrades accordingly.
 */
import type { Candle, MarketWsMessage } from "@/lib/api/generated";
import { useRealtimeStore } from "./store";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const STORAGE_KEY = "tp.auth";

type CandleListener = (c: Candle) => void;

function accessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as { access: string }).access : null;
  } catch {
    return null;
  }
}

class MarketSocket {
  private ws: WebSocket | null = null;
  private wanted = new Set<number>();
  private refs = new Map<number, number>();
  private backoff = 1000;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private candleListeners = new Set<CandleListener>();

  start(): () => void {
    if (this.running) return () => this.stop();
    this.running = true;
    this.connect();
    return () => this.stop();
  }

  stop() {
    this.running = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.ws?.close();
    this.ws = null;
    useRealtimeStore.getState().setWsState("disconnected");
  }

  /** Reference-counted subscription; returns an unsubscribe. */
  subscribe(ids: number[]): () => void {
    for (const id of ids) {
      this.refs.set(id, (this.refs.get(id) ?? 0) + 1);
      this.wanted.add(id);
    }
    this.send({ action: "subscribe", instrument_ids: ids });
    return () => {
      const gone: number[] = [];
      for (const id of ids) {
        const n = (this.refs.get(id) ?? 1) - 1;
        if (n <= 0) {
          this.refs.delete(id);
          this.wanted.delete(id);
          gone.push(id);
        } else this.refs.set(id, n);
      }
      if (gone.length) this.send({ action: "unsubscribe", instrument_ids: gone });
    };
  }

  onCandle(fn: CandleListener): () => void {
    this.candleListeners.add(fn);
    return () => {
      this.candleListeners.delete(fn);
    };
  }

  private send(msg: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  private connect() {
    if (!this.running) return;
    const token = accessToken();
    const store = useRealtimeStore.getState();
    if (!token) {
      store.setWsState("auth_required");
      this.scheduleReconnect();
      return;
    }
    store.setWsState("connecting");
    const ws = new WebSocket(`${WS_URL}/ws/market?token=${encodeURIComponent(token)}`);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      this.backoff = 1000;
      useRealtimeStore.getState().setWsState("connected");
      if (this.wanted.size) this.send({ action: "subscribe", instrument_ids: [...this.wanted] });
    };
    ws.onmessage = (ev) => void this.handle(ev.data);
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ws = null;
      const st = useRealtimeStore.getState();
      st.setWsState(ev.code === 4401 ? "auth_required" : "disconnected");
      st.setCollector(null);
      this.scheduleReconnect();
    };
    ws.onerror = () => {
      /* onclose follows */
    };
  }

  private scheduleReconnect() {
    if (!this.running) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.connect(), this.backoff);
    this.backoff = Math.min(this.backoff * 2, 30_000);
  }

  private async handle(data: unknown) {
    let text: string;
    if (typeof data === "string") text = data;
    else if (data instanceof ArrayBuffer) text = new TextDecoder().decode(data);
    else if (data instanceof Blob) text = await data.text();
    else return;
    let msg: MarketWsMessage;
    try {
      msg = JSON.parse(text) as MarketWsMessage;
    } catch {
      return;
    }
    const st = useRealtimeStore.getState();
    switch (msg.type) {
      case "quote": {
        const { type: _t, ...quote } = msg;
        void _t;
        st.putQuote(quote);
        break;
      }
      case "candle": {
        const { type: _t, ...candle } = msg;
        void _t;
        this.candleListeners.forEach((fn) => fn(candle));
        break;
      }
      case "status":
        st.setCollector(msg.collector);
        break;
      case "subscribed":
        st.setSubscribed(msg.instrument_ids);
        break;
    }
  }
}

export const marketSocket = new MarketSocket();
