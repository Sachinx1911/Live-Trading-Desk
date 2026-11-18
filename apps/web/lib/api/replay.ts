"use client";

/**
 * Historical replay sessions (ephemeral, in-process on the API). Mirrors
 * apps/api/src/api/routers/replay.py. Sessions are created and deleted here; the bar-by-bar
 * stream and the transport commands go over /ws/replay/{session_id} (lib/ws/replay.ts), with
 * the REST control endpoint kept as the fallback when the socket is down.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ReplayControlIn, ReplaySessionIn, ReplaySessionOut, ReplayState } from "./generated";

export const replayKeys = {
  list: ["replay", "sessions"] as const,
  session: (id: string) => ["replay", "sessions", id] as const,
};

/** Hard limit enforced by the API (`MAX_SPEED` in api/replay/session.py). */
export const REPLAY_MAX_SPEED = 600;

export function useReplaySessions(enabled = true) {
  return useQuery({
    queryKey: replayKeys.list,
    queryFn: () => api<ReplaySessionOut[]>("/replay/sessions"),
    enabled,
    staleTime: 10_000,
  });
}

export function useReplaySession(id: string | null) {
  return useQuery({
    queryKey: replayKeys.session(id ?? ""),
    queryFn: () => api<ReplaySessionOut>(`/replay/sessions/${id}`),
    enabled: id != null,
  });
}

export function useCreateReplaySession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ReplaySessionIn) =>
      api<ReplaySessionOut>("/replay/sessions", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: replayKeys.list }),
  });
}

export function useDeleteReplaySession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/replay/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: replayKeys.list }),
  });
}

/** REST transport control; used only when the socket cannot carry the command. */
export function useReplayControl(id: string | null) {
  return useMutation({
    mutationFn: (body: ReplayControlIn) =>
      api<ReplayState>(`/replay/sessions/${id}/control`, { method: "POST", body: JSON.stringify(body) }),
  });
}

/**
 * Fire-and-forget delete for page unload (`pagehide`), where React Query is already gone.
 * `keepalive` lets the request outlive the document.
 */
export function deleteReplaySessionOnUnload(id: string) {
  if (typeof window === "undefined") return;
  let access: string | null = null;
  try {
    const raw = window.localStorage.getItem("tp.auth");
    access = raw ? (JSON.parse(raw) as { access: string }).access : null;
  } catch {
    access = null;
  }
  if (!access) return;
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  void fetch(`${base}/api/v1/replay/sessions/${id}`, {
    method: "DELETE",
    headers: { authorization: `Bearer ${access}` },
    keepalive: true,
  }).catch(() => {
    /* best effort; the API sweeps idle sessions anyway */
  });
}
