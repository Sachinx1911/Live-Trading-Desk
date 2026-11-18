"use client";

/** Market regime hooks (Module 6): deterministic labels computed by the worker, read-only here. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { RegimeResponse, RegimeSummaryRow } from "./generated";

export const regimeKeys = {
  summary: ["regime", "summary"] as const,
  one: (id: number, days: number) => ["regime", id, days] as const,
};

export function useRegimeSummary() {
  return useQuery({
    queryKey: regimeKeys.summary,
    queryFn: () => api<RegimeSummaryRow[]>("/market/regime/summary"),
    refetchInterval: 60_000,
  });
}

export function useRegime(instrumentId: number | null, days = 30) {
  return useQuery({
    queryKey: regimeKeys.one(instrumentId ?? 0, days),
    queryFn: () => api<RegimeResponse>(`/market/regime?instrument_id=${instrumentId}&days=${days}`),
    enabled: instrumentId != null,
    refetchInterval: 60_000,
  });
}

export function useRecomputeRegime() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<unknown>("/market/regime/recompute", { method: "POST" }),
    onSuccess: () => {
      // The job runs in the worker; refetch after a short delay so the tile picks it up.
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["regime"] }), 4000);
    },
  });
}
