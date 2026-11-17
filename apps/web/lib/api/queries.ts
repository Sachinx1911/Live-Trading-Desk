"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api, setTokens } from "./client";
import type {
  HealthResponse,
  LoginRequest,
  ProvidersResponse,
  TokenResponse,
  User,
} from "./generated";

export const queryKeys = {
  me: ["auth", "me"] as const,
  providers: ["providers"] as const,
  health: ["health"] as const,
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
