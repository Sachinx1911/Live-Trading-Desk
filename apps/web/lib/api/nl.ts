"use client";

/** Phase 5 hooks: natural-language strategy builder (POST /strategies/generate …). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  NlAnswerRequest,
  NlDraft,
  NlGenerateRequest,
  NlSaveRequest,
  StrategyVersion,
} from "./generated";

export const nlKeys = {
  draft: (id: string) => ["nl", "draft", id] as const,
};

export function useNlDraft(draftId: string | null) {
  return useQuery({
    queryKey: nlKeys.draft(draftId ?? ""),
    queryFn: () => api<NlDraft>(`/strategies/generate/${draftId}`),
    enabled: draftId != null,
  });
}

export function useGenerateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NlGenerateRequest) =>
      api<NlDraft>("/strategies/generate", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (d) => qc.setQueryData(nlKeys.draft(d.draft_id), d),
  });
}

export function useAnswerDraft(draftId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NlAnswerRequest) =>
      api<NlDraft>(`/strategies/generate/${draftId}/answer`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (d) => qc.setQueryData(nlKeys.draft(d.draft_id), d),
  });
}

export function useSaveDraft(draftId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NlSaveRequest) =>
      api<StrategyVersion>(`/strategies/generate/${draftId}/save`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["strategies"] });
      if (draftId) void qc.invalidateQueries({ queryKey: nlKeys.draft(draftId) });
    },
  });
}
