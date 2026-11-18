"use client";

/**
 * Historical data import hooks (POST/GET /historical/imports).
 *
 * The shared `api()` client only speaks JSON (it forces `content-type: application/json`
 * whenever a body is present), so the upload goes through `apiMultipart()` below. It reads
 * the same stored session as the client and, on a 401, delegates to the client's own
 * refresh-or-redirect path by calling `/auth/me` before retrying once.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_URL, api, ApiRequestError } from "./client";
import type { ApiError, ImportJobOut, ImportMapping, ImportResponse, User } from "./generated";

/** Same key the client persists tokens under (lib/api/client.ts STORAGE_KEY). */
const STORAGE_KEY = "tp.auth";

function accessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? ((JSON.parse(raw) as { access: string }).access ?? null) : null;
  } catch {
    return null;
  }
}

async function apiMultipart<T>(path: string, form: FormData, retried = false): Promise<T> {
  const headers = new Headers({ accept: "application/json" });
  const token = accessToken();
  if (token) headers.set("authorization", `Bearer ${token}`);
  // No content-type: the browser sets multipart/form-data with the boundary.
  const res = await fetch(`${API_URL}/api/v1${path}`, { method: "POST", body: form, headers });
  if (res.status === 401) {
    if (!retried) {
      // Lets the JSON client refresh the token (or redirect to /login) and then retry.
      await api<User>("/auth/me");
      return apiMultipart<T>(path, form, true);
    }
    throw new ApiRequestError(401, "unauthorized", "Session expired");
  }
  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as ApiError & { detail?: unknown };
      code = err.error?.code ?? code;
      message =
        err.error?.message ?? (typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail ?? message));
    } catch {
      /* non-JSON error body */
    }
    throw new ApiRequestError(res.status, code, message);
  }
  return (await res.json()) as T;
}

export const importKeys = {
  jobs: ["historical", "imports"] as const,
  job: (id: number) => ["historical", "imports", id] as const,
};

export function useImportJobs(limit = 50) {
  return useQuery({
    queryKey: importKeys.jobs,
    queryFn: () => api<ImportJobOut[]>(`/historical/imports?limit=${limit}`),
    refetchInterval: 15_000,
  });
}

export function useImportJob(id: number | null) {
  return useQuery({
    queryKey: importKeys.job(id ?? 0),
    queryFn: () => api<ImportJobOut>(`/historical/imports/${id}`),
    enabled: id != null,
  });
}

export type UploadImportArgs = { file: File; mapping: ImportMapping; commit: boolean };

/** `commit=false` is a dry run (parse + report only); `commit=true` writes candles (owner only). */
export function useUploadImport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, mapping, commit }: UploadImportArgs) => {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("mapping", JSON.stringify(mapping));
      return apiMultipart<ImportResponse>(`/historical/imports?commit=${commit ? "true" : "false"}`, form);
    },
    onSuccess: (res) => {
      if (res.committed) void qc.invalidateQueries({ queryKey: importKeys.jobs });
    },
  });
}
