"use client";

/** Phase 4 hooks: backtest jobs, results, trades, reports, optimisation / walk-forward. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  BacktestIn,
  BacktestJob,
  BacktestReport,
  BacktestResultOut,
  BacktestTrade,
  JobStatus,
  OptimizationIn,
  OptimizationJob,
  OptimizationRow,
} from "./generated";

export const backtestKeys = {
  list: (versionId?: number, status?: JobStatus) => ["backtests", "list", versionId ?? 0, status ?? ""] as const,
  job: (id: number) => ["backtests", id] as const,
  results: (id: number) => ["backtests", id, "results"] as const,
  trades: (id: number, offset: number, limit: number) => ["backtests", id, "trades", offset, limit] as const,
  report: (id: number) => ["backtests", id, "report"] as const,
  optList: ["backtests", "optimizations"] as const,
  opt: (id: number) => ["backtests", "optimizations", id] as const,
  optResults: (id: number) => ["backtests", "optimizations", id, "results"] as const,
};

const LIVE: JobStatus[] = ["queued", "running"];
export const isLive = (s: JobStatus | undefined) => !!s && LIVE.includes(s);

export function useBacktests(versionId?: number, status?: JobStatus, limit = 100) {
  return useQuery({
    queryKey: backtestKeys.list(versionId, status),
    queryFn: () => {
      const p = new URLSearchParams();
      if (versionId != null) p.set("strategy_version_id", String(versionId));
      if (status) p.set("status", status);
      p.set("limit", String(limit));
      return api<BacktestJob[]>(`/backtests?${p.toString()}`);
    },
    refetchInterval: (q) => (q.state.data?.some((j) => isLive(j.status)) ? 2_000 : 15_000),
  });
}

export function useBacktest(id: number | null) {
  return useQuery({
    queryKey: backtestKeys.job(id ?? -1),
    queryFn: () => api<BacktestJob>(`/backtests/${id}`),
    enabled: id != null,
    refetchInterval: (q) => (isLive(q.state.data?.status) ? 2_000 : false),
  });
}

export function useBacktestResults(id: number | null, enabled = true) {
  return useQuery({
    queryKey: backtestKeys.results(id ?? -1),
    queryFn: () => api<BacktestResultOut>(`/backtests/${id}/results`),
    enabled: id != null && enabled,
    retry: false,
  });
}

export function useBacktestTrades(id: number | null, offset = 0, limit = 200, enabled = true) {
  return useQuery({
    queryKey: backtestKeys.trades(id ?? -1, offset, limit),
    queryFn: () => api<BacktestTrade[]>(`/backtests/${id}/trades?offset=${offset}&limit=${limit}`),
    enabled: id != null && enabled,
  });
}

export function useBacktestReport(id: number | null, enabled = true) {
  return useQuery({
    queryKey: backtestKeys.report(id ?? -1),
    queryFn: () => api<BacktestReport>(`/backtests/${id}/report`),
    enabled: id != null && enabled,
  });
}

export function useCreateBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BacktestIn) => api<BacktestJob>("/backtests", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }),
  });
}

export function useCancelBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<BacktestJob>(`/backtests/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }),
  });
}

export function useOptimizations(limit = 100) {
  return useQuery({
    queryKey: backtestKeys.optList,
    queryFn: () => api<OptimizationJob[]>(`/backtests/optimizations?limit=${limit}`),
    refetchInterval: (q) => (q.state.data?.some((j) => isLive(j.status)) ? 2_000 : 15_000),
  });
}

export function useOptimization(id: number | null) {
  return useQuery({
    queryKey: backtestKeys.opt(id ?? -1),
    queryFn: () => api<OptimizationJob>(`/backtests/optimizations/${id}`),
    enabled: id != null,
    refetchInterval: (q) => (isLive(q.state.data?.status) ? 2_000 : false),
  });
}

export function useOptimizationResults(id: number | null, enabled = true, limit = 500) {
  return useQuery({
    queryKey: backtestKeys.optResults(id ?? -1),
    queryFn: () => api<OptimizationRow[]>(`/backtests/optimizations/${id}/results?limit=${limit}`),
    enabled: id != null && enabled,
  });
}

export function useCreateOptimization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: OptimizationIn) =>
      api<OptimizationJob>("/backtests/optimizations", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }),
  });
}
