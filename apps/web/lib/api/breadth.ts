"use client";

/** Daily market breadth (Mark 1 Stage 3.6): derived rows computed by the worker. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { MarketBreadth, MarketBreadthList } from "./generated";

export function useBreadthLatest(universe = "NIFTY50") {
  return useQuery({
    queryKey: ["breadth", "latest", universe],
    queryFn: () => api<MarketBreadth | null>(`/market/breadth/latest?universe=${universe}`),
    refetchInterval: 5 * 60_000,
  });
}

export function useBreadthHistory(universe = "NIFTY50", limit = 120) {
  return useQuery({
    queryKey: ["breadth", "history", universe, limit],
    queryFn: () => api<MarketBreadthList>(`/market/breadth?universe=${universe}&limit=${limit}`),
    refetchInterval: 10 * 60_000,
  });
}

export function useRebuildBreadth() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { from_date: string; to_date?: string; universe?: string }) =>
      api<{ status: string }>("/market/breadth/rebuild", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["breadth"] }), 6000);
    },
  });
}
