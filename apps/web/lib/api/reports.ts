"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { DailyReport, DailyReportSummary } from "./generated";

export function useDailyReports(limit = 60) {
  return useQuery({
    queryKey: ["reports", "daily", "list", limit],
    queryFn: () => api<DailyReportSummary[]>(`/reports/daily?limit=${limit}`),
  });
}

export function useDailyReport(day: string | null) {
  return useQuery({
    queryKey: ["reports", "daily", day],
    queryFn: () => api<DailyReport>(day ? `/reports/daily/${day}` : "/reports/daily/latest"),
    retry: false,
  });
}

export function useGenerateDailyReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { day?: string | null; send?: boolean }) =>
      api<{ queued: boolean }>("/reports/daily/generate", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["reports", "daily"] }), 4000);
    },
  });
}
