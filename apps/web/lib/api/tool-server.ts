"use client";

/** Tool-server tokens and the tool-call log (Mark 1 Stage 4.1). Owner only. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ToolCallLog, ToolCallStatus, ToolToken, ToolTokenCreated, ToolTokenIn } from "./generated";

export const toolKeys = {
  all: ["tool-server"] as const,
  tokens: ["tool-server", "tokens"] as const,
  calls: (status: ToolCallStatus | "", limit: number) => ["tool-server", "calls", status, limit] as const,
};

export function useToolTokens() {
  return useQuery({ queryKey: toolKeys.tokens, queryFn: () => api<ToolToken[]>("/tool-tokens") });
}

export function useToolCalls(status: ToolCallStatus | "" = "", limit = 100) {
  return useQuery({
    queryKey: toolKeys.calls(status, limit),
    queryFn: () => api<ToolCallLog[]>(`/tool-calls?limit=${limit}${status ? `&status=${status}` : ""}`),
    refetchInterval: 15_000,
  });
}

export function useCreateToolToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ToolTokenIn) =>
      api<ToolTokenCreated>("/tool-tokens", { method: "POST", body: JSON.stringify(body) }),
    onSettled: () => void qc.invalidateQueries({ queryKey: toolKeys.tokens }),
  });
}

export function useRevokeToolToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<ToolToken>(`/tool-tokens/${id}/revoke`, { method: "POST" }),
    onSettled: () => void qc.invalidateQueries({ queryKey: toolKeys.all }),
  });
}
