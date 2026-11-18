"use client";

/** Market Scanner hooks (Phase 5): rule-based scans over the worker's daily snapshot. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  SavedScan,
  SavedScanIn,
  ScanFieldsResponse,
  ScanRunRequest,
  ScanRunResponse,
  ScanSnapshotInfo,
} from "./generated";

export const scannerKeys = {
  fields: ["scanner", "fields"] as const,
  presets: ["scanner", "presets"] as const,
  saved: ["scanner", "saved"] as const,
  snapshot: ["scanner", "snapshot"] as const,
  run: (req: ScanRunRequest) => ["scanner", "run", req] as const,
};

export function useScannerFields() {
  return useQuery({ queryKey: scannerKeys.fields, queryFn: () => api<ScanFieldsResponse>("/scanner/fields"), staleTime: 3_600_000 });
}

export function useScannerPresets() {
  return useQuery({ queryKey: scannerKeys.presets, queryFn: () => api<SavedScan[]>("/scanner/presets"), staleTime: 3_600_000 });
}

export function useSavedScans() {
  return useQuery({ queryKey: scannerKeys.saved, queryFn: () => api<SavedScan[]>("/scanner/saved") });
}

export function useScanSnapshot() {
  return useQuery({ queryKey: scannerKeys.snapshot, queryFn: () => api<ScanSnapshotInfo>("/scanner/snapshot"), refetchInterval: 60_000 });
}

/** The scan itself is a query keyed on the full request, so paging/sorting is cached and `placeholderData` keeps the last table while the next loads. */
export function useRunScan(req: ScanRunRequest, enabled = true) {
  return useQuery({
    queryKey: scannerKeys.run(req),
    queryFn: () => api<ScanRunResponse>("/scanner/run", { method: "POST", body: JSON.stringify(req) }),
    enabled,
    placeholderData: (prev) => prev,
    retry: false,
  });
}

export function useCreateSavedScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SavedScanIn) => api<SavedScan>("/scanner/saved", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: scannerKeys.saved }),
  });
}

export function useUpdateSavedScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: SavedScanIn & { id: number }) => api<SavedScan>(`/scanner/saved/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: scannerKeys.saved }),
  });
}

export function useDeleteSavedScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/scanner/saved/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: scannerKeys.saved }),
  });
}

/** Owner-only: enqueue a snapshot recompute in the worker; the snapshot pill refetches after a delay. */
export function useRequestSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (asOf?: string) => api<unknown>(`/scanner/snapshot${asOf ? `?as_of=${asOf}` : ""}`, { method: "POST" }),
    onSuccess: () => {
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["scanner"] }), 6000);
    },
  });
}
