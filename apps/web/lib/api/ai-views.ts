"use client";

/** JARVIS accuracy loop (Mark 1 Stage 4.6): recorded views, hit-rates and AI spend. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AiAccuracy } from "./generated";

export function useAiAccuracy(spendDays = 30) {
  return useQuery({
    queryKey: ["ai-views", "accuracy", spendDays],
    queryFn: () => api<AiAccuracy>(`/ai/accuracy?spend_days=${spendDays}&recent=100`),
    refetchInterval: 5 * 60_000,
  });
}

export function useRebuildAiViewScores() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ status: string }>("/ai/views/rebuild", { method: "POST" }),
    onSuccess: () => {
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["ai-views"] }), 5000);
    },
  });
}
