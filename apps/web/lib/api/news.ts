"use client";

/** Raw news headlines (Mark 1 Stage 3.5). Fetching runs in the worker; this only reads. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { NewsList, NewsSources } from "./generated";

export interface NewsFilter {
  source?: string;
  symbol?: string;
  q?: string;
  since?: string;
  limit?: number;
}

function qs(f: NewsFilter): string {
  const p = new URLSearchParams();
  if (f.source) p.set("source", f.source);
  if (f.symbol) p.set("symbol", f.symbol);
  if (f.q) p.set("q", f.q);
  if (f.since) p.set("since", f.since);
  p.set("limit", String(f.limit ?? 100));
  return p.toString();
}

export function useNews(f: NewsFilter, enabled = true) {
  return useQuery({
    queryKey: ["news", "list", f],
    queryFn: () => api<NewsList>(`/news?${qs(f)}`),
    enabled,
    refetchInterval: 5 * 60_000,
  });
}

export function useNewsSources() {
  return useQuery({
    queryKey: ["news", "sources"],
    queryFn: () => api<NewsSources>("/news/sources"),
    refetchInterval: 5 * 60_000,
  });
}

export function useIngestNews() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ status: string }>("/news/ingest", { method: "POST" }),
    onSuccess: () => {
      // The worker fetches the feeds; refetch after a short delay.
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["news"] }), 8000);
    },
  });
}
