"use client";

import { ChevronsRight, Pause, Play, Square, StepBack, StepForward } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { ReplayState, ReplayWsCommand } from "@/lib/api/generated";
import { formatTime } from "@/lib/format";
import type { ReplayWsState } from "@/lib/ws/replay";
import { cn } from "@/lib/utils";
import { SPEEDS } from "./ReplaySetupForm";

const STEPS = [1, 5, 20];

function StatusPill({ status, wsState }: { status: ReplayState["status"] | null; wsState: ReplayWsState }) {
  const down = wsState !== "connected";
  const label = down ? (wsState === "gone" ? "Session gone" : wsState === "auth_required" ? "Sign in" : "Disconnected") : status ?? "…";
  const tone = down
    ? "text-down"
    : status === "playing"
      ? "text-up"
      : status === "ended"
        ? "text-text-3"
        : "text-warn";
  return (
    <span className={cn("inline-flex h-5 items-center gap-1.5 rounded-full bg-raised px-2 text-[11px] font-medium uppercase tracking-wide", tone)}>
      <span className={cn("size-1.5 rounded-full", down ? "bg-down" : status === "playing" ? "bg-up" : status === "ended" ? "bg-text-3" : "bg-warn")} />
      {label}
    </span>
  );
}

/**
 * Play / pause / step / speed / seek for one session. Every control goes over the socket;
 * the slider seeks with a relative `step` (negative steps rebuild on the API) so it lands on
 * an exact bar index rather than a guessed timestamp.
 */
export function TransportBar({
  state,
  wsState,
  send,
  onEnd,
  ending,
}: {
  state: ReplayState | null;
  wsState: ReplayWsState;
  send: (cmd: ReplayWsCommand) => boolean;
  onEnd: () => void;
  ending: boolean;
}) {
  const connected = wsState === "connected" && state != null;
  const playing = state?.status === "playing";
  const ended = state?.status === "ended";
  const total = state?.bars ?? 0;
  const cursor = state?.cursor ?? 0;
  // Slider follows the live cursor unless the user is dragging it.
  const [drag, setDrag] = useState<number | null>(null);
  // The API acknowledges set_speed only with the next state frame; show the chosen value meanwhile.
  const serverSpeed = state?.speed ?? 60;
  const [local, setLocal] = useState<{ server: number; chosen: number }>({ server: serverSpeed, chosen: serverSpeed });
  const speed = local.server === serverSpeed ? local.chosen : serverSpeed;
  const setSpeed = (x: number) => setLocal({ server: serverSpeed, chosen: x });

  const seekTo = (target: number) => {
    const n = Math.max(0, Math.min(total, target)) - cursor;
    if (n !== 0) send({ type: "step", bars: n });
  };

  return (
    <div className="flex flex-col gap-2 border-t border-border px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="icon-sm"
          variant={playing ? "default" : "primary"}
          aria-label={playing ? "Pause" : "Play"}
          disabled={!connected || ended}
          onClick={() => send({ type: playing ? "pause" : "play" })}
        >
          {playing ? <Pause /> : <Play />}
        </Button>
        <div className="flex items-center gap-0.5">
          <Button size="xs" variant="ghost" disabled={!connected || cursor === 0} aria-label="Step back 1 bar" onClick={() => send({ type: "step", bars: -1 })}>
            <StepBack /> 1
          </Button>
          {STEPS.map((n) => (
            <Button key={n} size="xs" variant="ghost" disabled={!connected || ended} aria-label={`Step ${n} bars`} onClick={() => send({ type: "step", bars: n })}>
              {n === 1 ? <StepForward /> : <ChevronsRight />} {n}
            </Button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-[11px] text-text-3">
          Speed
          <select
            aria-label="Replay speed"
            className="h-6 rounded-[var(--r-pill)] border border-border bg-raised px-1.5 text-[12px] text-text-1 tabular"
            value={speed}
            disabled={!connected}
            onChange={(e) => {
              const x = Number(e.target.value);
              setSpeed(x);
              send({ type: "set_speed", x });
            }}
          >
            {SPEEDS.map((s) => (
              <option key={s.x} value={s.x}>{s.label}</option>
            ))}
            {!SPEEDS.some((s) => s.x === speed) && <option value={speed}>{speed}×</option>}
          </select>
        </label>
        <div className="ml-auto flex items-center gap-2">
          <span className="tabular text-[12px] text-text-2">
            {state?.cursor_ts ? formatTime(state.cursor_ts) : "—"}
          </span>
          <span className="tabular text-[11px] text-text-3">
            bar {cursor} / {total}
          </span>
          <StatusPill status={state?.status ?? null} wsState={wsState} />
          <Button size="xs" variant="destructive" onClick={onEnd} disabled={ending} aria-label="End replay">
            <Square /> End
          </Button>
        </div>
      </div>
      <input
        type="range"
        aria-label="Seek to bar"
        min={0}
        max={Math.max(total, 1)}
        step={1}
        value={drag ?? cursor}
        disabled={!connected || total === 0}
        onChange={(e) => setDrag(Number(e.target.value))}
        onPointerUp={() => {
          if (drag != null) seekTo(drag);
          setDrag(null);
        }}
        onKeyUp={() => {
          if (drag != null) seekTo(drag);
          setDrag(null);
        }}
        className="h-1 w-full cursor-pointer accent-[var(--accent)]"
      />
    </div>
  );
}
