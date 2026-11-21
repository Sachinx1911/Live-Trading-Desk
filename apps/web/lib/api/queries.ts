"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiRequestError, setTokens } from "./client";
import type {
  BrokerAccountIn,
  BrokerCode,
  BrokerLoginUrl,
  BrokerSessionStatus,
  CandlesResponse,
  CollectorHealth,
  CoverageRow,
  HealthResponse,
  Instrument,
  LoginRequest,
  OiChangeResponse,
  OptionChainResponse,
  ProvidersResponse,
  QuotesResponse,
  Timeframe,
  TokenResponse,
  User,
} from "./generated";

export const queryKeys = {
  me: ["auth", "me"] as const,
  providers: ["providers"] as const,
  health: ["health"] as const,
  brokers: ["brokers"] as const,
};

export function useMe(enabled = true) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api<User>("/auth/me"),
    enabled,
    retry: false,
  });
}

export function useProviders() {
  return useQuery({
    queryKey: queryKeys.providers,
    queryFn: () => api<ProvidersResponse>("/providers"),
    // Consumers want the list; the active provider is always first.
    select: (r) => r.providers,
    refetchInterval: 10_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api<HealthResponse>("/health", { auth: false }),
    refetchInterval: 30_000,
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: async (body: LoginRequest) => {
      const data = await api<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
        auth: false,
      });
      setTokens({ access: data.access_token, refresh: data.refresh_token });
      return data;
    },
  });
}

export function logout() {
  setTokens(null);
  // Full reload on purpose: drop every cached query and store.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  if (typeof window !== "undefined") window.location.assign("/login");
}

// --- Brokers (ADR-012: daily login) -----------------------------------------------------

export function useBrokers() {
  return useQuery({
    queryKey: queryKeys.brokers,
    queryFn: () => api<BrokerSessionStatus[]>("/brokers"),
    refetchInterval: 60_000,
  });
}

export function useUpsertBrokerAccount(code: BrokerCode) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BrokerAccountIn) =>
      api<BrokerSessionStatus>(`/brokers/${code}/account`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.brokers }),
  });
}

/** Returns the broker's OAuth URL; the caller performs a full-page navigation to it. */
export function useBrokerLoginUrl(code: BrokerCode) {
  return useMutation({
    mutationFn: () => api<BrokerLoginUrl>(`/brokers/${code}/login-url`),
  });
}

export function useBrokerLogout(code: BrokerCode) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<BrokerSessionStatus>(`/brokers/${code}/logout`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.brokers }),
  });
}

// --- Market data (Phase 2) ----------------------------------------------------------------


export const marketKeys = {
  search: (q: string, exchange?: string) => ["instruments", "search", q, exchange ?? ""] as const,
  instrument: (id: number) => ["instruments", id] as const,
  candles: (id: number, tf: Timeframe, limit: number) => ["candles", id, tf, limit] as const,
  quotes: (ids: number[]) => ["quotes", ids.join(",")] as const,
  coverage: (id?: number) => ["coverage", id ?? "all"] as const,
  expiries: (id: number) => ["chain", "expiries", id] as const,
  chain: (id: number, expiry?: string, at?: string) =>
    ["chain", id, expiry ?? "latest", at ?? "now"] as const,
  oiExpiries: (id: number, day: string) => ["oi-change", "expiries", id, day] as const,
  oiChange: (id: number, expiry: string, day: string, start: string, end: string) =>
    ["oi-change", id, expiry, day, start, end] as const,
  collector: ["collector"] as const,
};

export function useInstrumentSearch(q: string, exchange?: string, limit = 20) {
  const query = q.trim();
  return useQuery({
    queryKey: marketKeys.search(query, exchange),
    queryFn: () => {
      const p = new URLSearchParams({ q: query, limit: String(limit) });
      if (exchange) p.set("exchange", exchange);
      return api<Instrument[]>(`/instruments?${p.toString()}`);
    },
    enabled: query.length > 0,
    staleTime: 60_000,
  });
}

export function useInstrument(id: number | null) {
  return useQuery({
    queryKey: marketKeys.instrument(id ?? -1),
    queryFn: () => api<Instrument>(`/instruments/${id}`),
    enabled: id != null,
    staleTime: 5 * 60_000,
  });
}

export function useCandles(id: number | null, tf: Timeframe, limit = 500) {
  return useQuery({
    queryKey: marketKeys.candles(id ?? -1, tf, limit),
    queryFn: () =>
      api<CandlesResponse>(
        `/market/candles?instrument_id=${id}&timeframe=${tf}&limit=${limit}`,
      ),
    enabled: id != null,
    staleTime: 30_000,
  });
}

/** REST fallback for quotes; the WebSocket store is the primary source. */
export function useQuotes(ids: number[], enabled = true) {
  return useQuery({
    queryKey: marketKeys.quotes(ids),
    queryFn: () => api<QuotesResponse>(`/market/quotes?ids=${ids.join(",")}`),
    enabled: enabled && ids.length > 0,
    refetchInterval: 5_000,
  });
}

export function useCoverage(id?: number) {
  return useQuery({
    queryKey: marketKeys.coverage(id),
    queryFn: () => api<CoverageRow[]>(`/market/coverage${id != null ? `?instrument_id=${id}` : ""}`),
    refetchInterval: 60_000,
  });
}

export function useChainExpiries(underlyingId: number | null) {
  return useQuery({
    queryKey: marketKeys.expiries(underlyingId ?? -1),
    queryFn: () => api<string[]>(`/market/option-chain/expiries?underlying_id=${underlyingId}`),
    enabled: underlyingId != null,
    staleTime: 5 * 60_000,
  });
}

/** `at` (ISO datetime) asks for the last snapshot stored at or before that moment. */
export function useOptionChain(underlyingId: number | null, expiry?: string, at?: string) {
  return useQuery({
    queryKey: marketKeys.chain(underlyingId ?? -1, expiry, at),
    queryFn: () => {
      const p = new URLSearchParams({ underlying_id: String(underlyingId) });
      if (expiry) p.set("expiry", expiry);
      if (at) p.set("at", at);
      return api<OptionChainResponse>(`/market/option-chain?${p.toString()}`);
    },
    enabled: underlyingId != null,
    refetchInterval: at ? false : 60_000,
    retry: (count, err) => !(err instanceof ApiRequestError && err.status === 404) && count < 2,
  });
}

export function useCollector() {
  return useQuery({
    queryKey: marketKeys.collector,
    queryFn: () => api<CollectorHealth>("/market/collector"),
    refetchInterval: 10_000,
  });
}

// --- OI change (Mark 1, 1.2) -----------------------------------------------------------

export function useOiChangeExpiries(underlyingId: number | null, day: string) {
  return useQuery({
    queryKey: marketKeys.oiExpiries(underlyingId ?? -1, day),
    queryFn: () =>
      api<string[]>(`/market/oi-change/expiries?underlying_id=${underlyingId}&day=${day}`),
    enabled: underlyingId != null,
    staleTime: 60_000,
  });
}

export function useOiChange(
  underlyingId: number | null,
  expiry: string | undefined,
  day: string,
  start: string,
  end: string,
) {
  return useQuery({
    queryKey: marketKeys.oiChange(underlyingId ?? -1, expiry ?? "", day, start, end),
    queryFn: () => {
      const p = new URLSearchParams({
        underlying_id: String(underlyingId),
        expiry: expiry ?? "",
        day,
        start,
        end,
      });
      return api<OiChangeResponse>(`/market/oi-change?${p.toString()}`);
    },
    enabled: underlyingId != null && !!expiry,
    refetchInterval: 60_000,
    retry: (count, err) => !(err instanceof ApiRequestError && err.status === 404) && count < 2,
  });
}
