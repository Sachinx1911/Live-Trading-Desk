"use client";

/**
 * Owns one ReplaySocket for the life of a session and folds its frames into render state.
 * Frames are buffered and flushed once per animation frame so a 20-bar step or a 600× run
 * does not re-render the page per frame.
 *
 * Rewind handling: the API rebuilds its state deterministically and sends `rewound` followed
 * by a `state` (with the new cursor_ts). It does not re-send the bars before the cursor, so we
 * keep what we already received and drop everything at or after the new cursor:
 *   - view bars whose close (ts + timeframe) is after the cursor,
 *   - fills / closed trades at or after the cursor (they happen at a bar's open),
 *   - signals / orders / rejections after the cursor (they happen at a bar's close).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Candle,
  Quote,
  ReplayFill,
  ReplayOrder,
  ReplaySignal,
  ReplayState,
  ReplayTrade,
  ReplayWsCommand,
  ReplayWsMessage,
  Timeframe,
} from "@/lib/api/generated";
import { ReplaySocket, type ReplayWsState } from "@/lib/ws/replay";

/**
 * `ts` is the event's own time (shown). `seen` is the session's 1m clock when the event
 * arrived (the last quote's ts), which is what a rewind prunes by: fills and trades happen
 * at a bar's open (clock strictly before the new cursor), signals, orders and rejections at
 * a bar's close (clock at or before it).
 */
export type ReplayEvent =
  | { id: string; kind: "signal"; ts: string; seen: string; data: ReplaySignal }
  | { id: string; kind: "signal_rejected"; ts: string; seen: string; data: { kind: string; reasons: string[] } }
  | { id: string; kind: "order"; ts: string; seen: string; data: ReplayOrder }
  | { id: string; kind: "fill"; ts: string; seen: string; data: ReplayFill };

export interface SeenTrade {
  seen: string;
  data: ReplayTrade;
}

export interface ReplayStreamState {
  bars: Candle[];
  lastQuote: Quote | null;
  events: ReplayEvent[];
  trades: SeenTrade[];
  state: ReplayState | null;
  lastError: string | null;
}

const EMPTY: ReplayStreamState = { bars: [], lastQuote: null, events: [], trades: [], state: null, lastError: null };

export const TF_SECONDS: Partial<Record<Timeframe, number>> = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "30m": 1800,
  "1h": 3600,
  "1d": 86400,
};

const sec = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);

function prune(s: ReplayStreamState, cursorTs: string, tf: Timeframe): ReplayStreamState {
  const cur = sec(cursorTs);
  const dur = TF_SECONDS[tf] ?? 60;
  return {
    ...s,
    bars: s.bars.filter((b) => sec(b.ts) + dur <= cur),
    events: s.events.filter((e) => (e.kind === "fill" ? sec(e.seen) < cur : sec(e.seen) <= cur)),
    trades: s.trades.filter((t) => sec(t.seen) < cur),
    lastQuote: null,
  };
}

function apply(prev: ReplayStreamState, batch: ReplayWsMessage[], tf: Timeframe): ReplayStreamState {
  let s: ReplayStreamState = { ...prev, bars: [...prev.bars], events: [...prev.events], trades: [...prev.trades] };
  let pendingRewind = false;
  let seq = s.events.length;
  // The session's 1m clock: the latest quote ts (one quote per consumed 1m bar).
  let clock = s.lastQuote?.ts ?? s.state?.cursor_ts ?? new Date(0).toISOString();
  let lastSignalTs: string | null = null;
  for (const m of batch) {
    switch (m.type) {
      case "bar": {
        const { type: _t, ...c } = m;
        void _t;
        const last = s.bars[s.bars.length - 1];
        if (last && last.ts === c.ts) s.bars[s.bars.length - 1] = c;
        else if (!last || c.ts > last.ts) s.bars.push(c);
        break;
      }
      case "quote": {
        const { type: _t, ...q } = m;
        void _t;
        s.lastQuote = q;
        clock = q.ts;
        break;
      }
      case "signal": {
        const { type: _t, ...d } = m;
        void _t;
        lastSignalTs = d.ts;
        s.events.push({ id: `sig-${d.signal_id}`, kind: "signal", ts: d.ts, seen: clock, data: d });
        break;
      }
      case "signal_rejected":
        // Carries no timestamp; it always follows the signal it rejects.
        s.events.push({
          id: `rej-${seq++}-${clock}`,
          kind: "signal_rejected",
          ts: lastSignalTs ?? clock,
          seen: clock,
          data: { kind: m.kind, reasons: m.reasons },
        });
        break;
      case "order": {
        const { type: _t, ...d } = m;
        void _t;
        const id = `ord-${d.order_id}-${d.status}`;
        if (!s.events.some((e) => e.id === id)) s.events.push({ id, kind: "order", ts: d.created_at, seen: clock, data: d });
        break;
      }
      case "fill": {
        const { type: _t, ...d } = m;
        void _t;
        s.events.push({ id: `fill-${d.order_id}-${d.ts}-${seq++}`, kind: "fill", ts: d.ts, seen: clock, data: d });
        break;
      }
      case "trade": {
        const { type: _t, ...d } = m;
        void _t;
        s.trades.push({ seen: clock, data: d });
        break;
      }
      case "position":
        // The authoritative open position comes with every `state` (overlay.position).
        break;
      case "rewound":
        pendingRewind = true;
        break;
      case "state":
        if (pendingRewind) {
          pendingRewind = false;
          if (m.cursor_ts) s = prune(s, m.cursor_ts, tf);
          else s = { ...s, bars: [], events: [], trades: [], lastQuote: null };
        }
        s.state = m;
        break;
      case "error":
        s.lastError = m.message;
        break;
    }
  }
  return s;
}

export function useReplayStream(sessionId: string | null, timeframe: Timeframe) {
  const [data, setData] = useState<ReplayStreamState>(EMPTY);
  const [wsState, setWsState] = useState<ReplayWsState>("disconnected");
  const socketRef = useRef<ReplaySocket | null>(null);
  const bufferRef = useRef<ReplayWsMessage[]>([]);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    const sock = new ReplaySocket(sessionId);
    socketRef.current = sock;
    const flush = () => {
      rafRef.current = null;
      const batch = bufferRef.current;
      bufferRef.current = [];
      if (batch.length) setData((prev) => apply(prev, batch, timeframe));
    };
    const offMsg = sock.onMessage((m) => {
      bufferRef.current.push(m);
      if (rafRef.current == null) rafRef.current = requestAnimationFrame(flush);
    });
    const offState = sock.onState(setWsState);
    const stop = sock.start();
    return () => {
      offMsg();
      offState();
      stop();
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      bufferRef.current = [];
      socketRef.current = null;
      // A new session starts from an empty stream.
      setData(EMPTY);
    };
  }, [sessionId, timeframe]);

  const send = useMemo(
    () => (cmd: ReplayWsCommand) => socketRef.current?.send(cmd) ?? false,
    [],
  );
  const clearError = useMemo(() => () => setData((p) => (p.lastError ? { ...p, lastError: null } : p)), []);

  return { ...data, wsState, send, clearError };
}
