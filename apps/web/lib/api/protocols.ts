"use client";

/** Trading protocols (Mark 1 Stage 3.1): definitions, the action catalogue and runs. Runs
 *  execute in the worker; the page polls the run until it finishes. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  Protocol,
  ProtocolAction,
  ProtocolCreateIn,
  ProtocolRun,
  ProtocolUpdateIn,
} from "./generated";

export const protocolKeys = {
  list: ["protocols"] as const,
  actions: ["protocols", "actions"] as const,
  runs: ["protocols", "runs"] as const,
};

const OPEN = new Set(["running", "awaiting_confirmation"]);

export function useProtocols() {
  return useQuery({ queryKey: protocolKeys.list, queryFn: () => api<Protocol[]>("/protocols") });
}

export function useProtocolActions() {
  return useQuery({
    queryKey: protocolKeys.actions,
    queryFn: () => api<ProtocolAction[]>("/protocols/actions"),
    staleTime: 5 * 60_000,
  });
}

export function useProtocolRuns(limit = 30) {
  return useQuery({
    queryKey: [...protocolKeys.runs, limit],
    queryFn: () => api<ProtocolRun[]>(`/protocols/runs?limit=${limit}`),
    // Poll fast while any run is open, slowly otherwise.
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => OPEN.has(r.status)) ? 1_500 : 15_000),
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: protocolKeys.list });
    void qc.invalidateQueries({ queryKey: protocolKeys.runs });
  };
}

export function useRunProtocol() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (code: string) =>
      api<ProtocolRun>(`/protocols/${code}/run`, { method: "POST", body: JSON.stringify({ trigger: "button" }) }),
    onSettled: inv,
  });
}

export function useConfirmRun() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api<ProtocolRun>(`/protocols/runs/${id}/confirm`, { method: "POST" }),
    onSettled: inv,
  });
}

export function useCancelRun() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (id: number) =>
      api<ProtocolRun>(`/protocols/runs/${id}/cancel`, {
        method: "POST",
        body: JSON.stringify({ reason: "cancelled by user" }),
      }),
    onSettled: inv,
  });
}

export function useSaveProtocol() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ code, body, isNew }: { code: string; body: ProtocolUpdateIn; isNew: boolean }) =>
      isNew
        ? api<Protocol>("/protocols", { method: "POST", body: JSON.stringify({ ...body, code } satisfies ProtocolCreateIn) })
        : api<Protocol>(`/protocols/${code}`, { method: "PUT", body: JSON.stringify(body) }),
    onSettled: inv,
  });
}

export function useDeleteProtocol() {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: (code: string) => api<void>(`/protocols/${code}`, { method: "DELETE" }),
    onSettled: inv,
  });
}
