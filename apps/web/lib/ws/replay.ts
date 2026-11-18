"use client";

/**
 * Client for /ws/replay/{session_id}. One socket per replay session (not a singleton: the
 * page owns the lifetime). Frames are binary JSON; reconnects with backoff while the session
 * exists. Close code 4404 means the session is gone on the API (idle sweep or deleted) and
 * the client stops trying. Nothing is invented here: when the socket is down the state says
 * so and the transport controls are disabled.
 */
import type { ReplayWsCommand, ReplayWsMessage } from "@/lib/api/generated";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const STORAGE_KEY = "tp.auth";

export type ReplayWsState = "connecting" | "connected" | "disconnected" | "auth_required" | "gone";

type MessageListener = (m: ReplayWsMessage) => void;
type StateListener = (s: ReplayWsState) => void;

function accessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as { access: string }).access : null;
  } catch {
    return null;
  }
}

export class ReplaySocket {
  private ws: WebSocket | null = null;
  private backoff = 1000;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private messageListeners = new Set<MessageListener>();
  private stateListeners = new Set<StateListener>();
  state: ReplayWsState = "disconnected";

  constructor(readonly sessionId: string) {}

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
    const ws = this.ws;
    this.ws = null;
    ws?.close();
    this.setState("disconnected");
  }

  onMessage(fn: MessageListener): () => void {
    this.messageListeners.add(fn);
    return () => {
      this.messageListeners.delete(fn);
    };
  }

  onState(fn: StateListener): () => void {
    this.stateListeners.add(fn);
    fn(this.state);
    return () => {
      this.stateListeners.delete(fn);
    };
  }

  /** Returns false when the socket is not open (caller may fall back to REST control). */
  send(cmd: ReplayWsCommand): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(cmd));
    return true;
  }

  private setState(s: ReplayWsState) {
    if (this.state === s) return;
    this.state = s;
    this.stateListeners.forEach((fn) => fn(s));
  }

  private connect() {
    if (!this.running) return;
    const token = accessToken();
    if (!token) {
      this.setState("auth_required");
      this.scheduleReconnect();
      return;
    }
    this.setState("connecting");
    const ws = new WebSocket(
      `${WS_URL}/ws/replay/${encodeURIComponent(this.sessionId)}?token=${encodeURIComponent(token)}`,
    );
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      if (this.ws !== ws) return;
      this.backoff = 1000;
      this.setState("connected");
    };
    ws.onmessage = (ev) => void this.handle(ev.data);
    ws.onclose = (ev) => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (ev.code === 4404) {
        // Session no longer exists on the API: do not loop on it.
        this.running = false;
        this.setState("gone");
        return;
      }
      this.setState(ev.code === 4401 ? "auth_required" : "disconnected");
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
    let msg: ReplayWsMessage;
    try {
      msg = JSON.parse(text) as ReplayWsMessage;
    } catch {
      return;
    }
    this.messageListeners.forEach((fn) => fn(msg));
  }
}
