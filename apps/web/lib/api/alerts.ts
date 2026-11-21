"use client";

/** Proactive alerts (Mark 1 Stage 3.2): produced by the worker and the paper trader. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AlertAckAll, AlertItem, AlertUnreadCount } from "./generated";

export const alertKeys = {
  all: ["alerts"] as const,
  list: (unackOnly: boolean, limit: number) => ["alerts", "list", unackOnly, limit] as const,
  unread: ["alerts", "unread"] as const,
};

export function useAlerts(unackOnly = false, limit = 100) {
  return useQuery({
    queryKey: alertKeys.list(unackOnly, limit),
    queryFn: () => api<AlertItem[]>(`/alerts?limit=${limit}${unackOnly ? "&unacknowledged=true" : ""}`),
    refetchInterval: 30_000,
  });
}

export function useUnreadAlerts() {
  return useQuery({
    queryKey: alertKeys.unread,
    queryFn: () => api<AlertUnreadCount>("/alerts/unread-count"),
    refetchInterval: 30_000,
  });
}

export function useAckAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<AlertItem>(`/alerts/${id}/ack`, { method: "POST" }),
    onSettled: () => void qc.invalidateQueries({ queryKey: alertKeys.all }),
  });
}

export function useAckAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<AlertAckAll>("/alerts/ack-all", { method: "POST" }),
    onSettled: () => void qc.invalidateQueries({ queryKey: alertKeys.all }),
  });
}
