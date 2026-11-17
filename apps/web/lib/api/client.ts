"use client";

import type { ApiError, RefreshRequest, TokenResponse } from "./generated";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STORAGE_KEY = "tp.auth";

type Tokens = { access: string; refresh: string };

let memory: Tokens | null = null;

function load(): Tokens | null {
  if (memory) return memory;
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    memory = raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    memory = null;
  }
  return memory;
}

const listeners = new Set<() => void>();

export function subscribeSession(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) {
      memory = null;
      cb();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

export function setTokens(t: Tokens | null) {
  memory = t;
  if (typeof window === "undefined") return;
  if (t) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(t));
  else window.localStorage.removeItem(STORAGE_KEY);
  listeners.forEach((l) => l());
}

export function hasSession(): boolean {
  return load() !== null;
}

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

function redirectToLogin() {
  setTokens(null);
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const next = encodeURIComponent(window.location.pathname);
    // Full reload on purpose: this runs outside React (fetch wrapper) and must clear all state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${next}`);
  }
}

async function tryRefresh(): Promise<boolean> {
  const t = load();
  if (!t) return false;
  const body: RefreshRequest = { refresh_token: t.refresh };
  const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) return false;
  const data = (await res.json()) as TokenResponse;
  setTokens({ access: data.access_token, refresh: data.refresh_token });
  return true;
}

export async function api<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
  retried = false,
): Promise<T> {
  const { auth = true, ...rest } = init;
  const headers = new Headers(rest.headers);
  headers.set("accept", "application/json");
  if (rest.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const t = load();
  if (auth && t) headers.set("authorization", `Bearer ${t.access}`);

  const res = await fetch(`${API_URL}/api/v1${path}`, { ...rest, headers });

  if (res.status === 401 && auth) {
    if (!retried && (await tryRefresh())) return api<T>(path, init, true);
    redirectToLogin();
    throw new ApiRequestError(401, "unauthorized", "Session expired");
  }
  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as ApiError;
      code = err.error?.code ?? code;
      message = err.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiRequestError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
