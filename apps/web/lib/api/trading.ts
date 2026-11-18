"use client";

/** Phase 3 hooks: paper trading, risk limits, kill switch, strategy library, events. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  Activation,
  ActivationIn,
  KillIn,
  KillStatus,
  KillSwitchEvent,
  KillSwitchScope,
  MarketEvent,
  MarketEventIn,
  PaperAccount,
  PaperAccountIn,
  PaperOrder,
  PaperOrderEvent,
  PaperPosition,
  PaperTrade,
  RiskLimits,
  RiskLimitsResponse,
  StopActivationIn,
  Strategy,
  StrategyIn,
  StrategyVersion,
  TransitionIn,
  StrategyApproval,
  VersionReadiness,
  ValidationReport,
  VersionIn,
} from "./generated";

export const tradingKeys = {
  accounts: ["paper", "accounts"] as const,
  account: (id: number) => ["paper", "accounts", id] as const,
  orders: (id: number, openOnly: boolean) => ["paper", id, "orders", openOnly] as const,
  orderEvents: (id: number) => ["paper", "orders", id, "events"] as const,
  positions: (id: number, closed: boolean) => ["paper", id, "positions", closed] as const,
  trades: (id: number) => ["paper", id, "trades"] as const,
  activations: (id: number, all: boolean) => ["paper", id, "activations", all] as const,
  limits: (id: number) => ["risk", "limits", id] as const,
  kill: (accountId?: number, strategyId?: number) => ["risk", "kill", accountId ?? 0, strategyId ?? 0] as const,
  killEvents: ["risk", "kill", "events"] as const,
  strategies: (archived: boolean) => ["strategies", archived] as const,
  strategy: (id: number) => ["strategies", id] as const,
  versions: (id: number) => ["strategies", id, "versions"] as const,
  version: (id: number) => ["strategies", "versions", id] as const,
  events: (frm?: string, to?: string) => ["events", frm ?? "", to ?? ""] as const,
};

const PAPER_POLL = 5_000;

// ---------------------------------------------------------------- paper accounts
export function usePaperAccounts() {
  return useQuery({
    queryKey: tradingKeys.accounts,
    queryFn: () => api<PaperAccount[]>("/paper/accounts"),
    refetchInterval: PAPER_POLL,
  });
}

export function usePaperAccount(id: number | null) {
  return useQuery({
    queryKey: tradingKeys.account(id ?? -1),
    queryFn: () => api<PaperAccount>(`/paper/accounts/${id}`),
    enabled: id != null,
    refetchInterval: PAPER_POLL,
  });
}

export function useCreatePaperAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PaperAccountIn) =>
      api<PaperAccount>("/paper/accounts", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tradingKeys.accounts }),
  });
}

export function useResetPaperAccount(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PaperAccountIn) =>
      api<PaperAccount>(`/paper/accounts/${id}/reset`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["paper"] }),
  });
}

export function usePaperOrders(accountId: number | null, openOnly = false, limit = 200) {
  return useQuery({
    queryKey: tradingKeys.orders(accountId ?? -1, openOnly),
    queryFn: () => api<PaperOrder[]>(`/paper/accounts/${accountId}/orders?open_only=${openOnly}&limit=${limit}`),
    enabled: accountId != null,
    refetchInterval: PAPER_POLL,
  });
}

export function usePaperOrderEvents(orderId: number | null) {
  return useQuery({
    queryKey: tradingKeys.orderEvents(orderId ?? -1),
    queryFn: () => api<PaperOrderEvent[]>(`/paper/orders/${orderId}/events`),
    enabled: orderId != null,
    refetchInterval: 10_000,
  });
}

export function usePaperPositions(accountId: number | null, includeClosed = false) {
  return useQuery({
    queryKey: tradingKeys.positions(accountId ?? -1, includeClosed),
    queryFn: () => api<PaperPosition[]>(`/paper/accounts/${accountId}/positions?include_closed=${includeClosed}`),
    enabled: accountId != null,
    refetchInterval: PAPER_POLL,
  });
}

export function usePaperTrades(accountId: number | null, limit = 500) {
  return useQuery({
    queryKey: tradingKeys.trades(accountId ?? -1),
    queryFn: () => api<PaperTrade[]>(`/paper/accounts/${accountId}/trades?limit=${limit}`),
    enabled: accountId != null,
    refetchInterval: 10_000,
  });
}

export function useActivations(accountId: number | null, allStatuses = false) {
  return useQuery({
    queryKey: tradingKeys.activations(accountId ?? -1, allStatuses),
    queryFn: () => api<Activation[]>(`/paper/accounts/${accountId}/activations?all_statuses=${allStatuses}`),
    enabled: accountId != null,
    refetchInterval: PAPER_POLL,
  });
}

export function useActivateStrategy(accountId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ActivationIn) =>
      api<Activation>(`/paper/accounts/${accountId}/activations`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["paper"] });
      void qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });
}

export function useStopActivation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: StopActivationIn & { id: number }) =>
      api<Activation>(`/paper/activations/${id}/stop`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["paper"] }),
  });
}

export function useToggleActivation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<Activation>(`/paper/activations/${id}/pause`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["paper"] }),
  });
}

// ---------------------------------------------------------------- risk
export function usePaperRiskLimits(accountId: number | null) {
  return useQuery({
    queryKey: tradingKeys.limits(accountId ?? -1),
    queryFn: () => api<RiskLimitsResponse>(`/risk/limits/paper/${accountId}`),
    enabled: accountId != null,
    refetchInterval: 60_000,
  });
}

export function useSavePaperRiskLimits(accountId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RiskLimits) =>
      api<RiskLimitsResponse>(`/risk/limits/paper/${accountId}`, { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tradingKeys.limits(accountId) }),
  });
}

export function useKillSwitch(accountId?: number, strategyId?: number) {
  return useQuery({
    queryKey: tradingKeys.kill(accountId, strategyId),
    queryFn: () => {
      const p = new URLSearchParams();
      if (accountId != null) p.set("account_id", String(accountId));
      if (strategyId != null) p.set("strategy_id", String(strategyId));
      const qs = p.toString();
      return api<KillStatus[]>(`/risk/kill-switch${qs ? `?${qs}` : ""}`);
    },
    refetchInterval: PAPER_POLL,
  });
}

export function useKillSwitchEvents() {
  return useQuery({
    queryKey: tradingKeys.killEvents,
    queryFn: () => api<KillSwitchEvent[]>("/risk/kill-switch/events"),
    refetchInterval: 10_000,
  });
}

export function useActivateKill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ scope, scopeId, ...body }: KillIn & { scope: KillSwitchScope; scopeId?: number }) =>
      api<KillStatus>(`/risk/kill-switch/${scope}${scopeId != null ? `?scope_id=${scopeId}` : ""}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk", "kill"] }),
  });
}

export function useClearKill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ scope, scopeId, ...body }: KillIn & { scope: KillSwitchScope; scopeId?: number }) =>
      api<KillStatus>(`/risk/kill-switch/${scope}${scopeId != null ? `?scope_id=${scopeId}` : ""}`, {
        method: "DELETE",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk", "kill"] }),
  });
}

// ---------------------------------------------------------------- strategies
export function useStrategies(includeArchived = false) {
  return useQuery({
    queryKey: tradingKeys.strategies(includeArchived),
    queryFn: () => api<Strategy[]>(`/strategies?include_archived=${includeArchived}`),
    refetchInterval: 30_000,
  });
}

export function useStrategy(id: number | null) {
  return useQuery({
    queryKey: tradingKeys.strategy(id ?? -1),
    queryFn: () => api<Strategy>(`/strategies/${id}`),
    enabled: id != null,
  });
}

export function useStrategyVersions(id: number | null) {
  return useQuery({
    queryKey: tradingKeys.versions(id ?? -1),
    queryFn: () => api<StrategyVersion[]>(`/strategies/${id}/versions`),
    enabled: id != null,
  });
}

export function useStrategyVersion(id: number | null) {
  return useQuery({
    queryKey: tradingKeys.version(id ?? -1),
    queryFn: () => api<StrategyVersion>(`/strategies/versions/${id}`),
    enabled: id != null,
  });
}

export function useCreateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StrategyIn) => api<Strategy>("/strategies", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });
}

export function useArchiveStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<Strategy>(`/strategies/${id}/archive`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });
}

export function useValidateDsl() {
  return useMutation({
    mutationFn: (dsl: Record<string, unknown>) =>
      api<ValidationReport>("/strategies/validate", { method: "POST", body: JSON.stringify({ dsl }) }),
  });
}

export function useCreateVersion(strategyId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: VersionIn) =>
      api<StrategyVersion>(`/strategies/${strategyId}/versions`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });
}

export function useEditVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ versionId, ...body }: VersionIn & { versionId: number }) =>
      api<StrategyVersion>(`/strategies/versions/${versionId}/edit`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategies"] }),
  });
}

export function useTransitionVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ versionId, ...body }: TransitionIn & { versionId: number }) =>
      api<StrategyVersion>(`/strategies/versions/${versionId}/transition`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["strategies"] });
      qc.invalidateQueries({ queryKey: ["approval"] });
    },
  });
}

export function useVersionReadiness(versionId: number | null) {
  return useQuery({
    queryKey: ["approval", "readiness", versionId],
    queryFn: () => api<VersionReadiness>(`/strategies/versions/${versionId}/readiness`),
    enabled: versionId != null,
  });
}

export function useVersionApprovals(versionId: number | null) {
  return useQuery({
    queryKey: ["approval", "log", versionId],
    queryFn: () => api<StrategyApproval[]>(`/strategies/versions/${versionId}/approvals`),
    enabled: versionId != null,
  });
}

// ---------------------------------------------------------------- events
export function useMarketEvents(frm?: string, to?: string) {
  return useQuery({
    queryKey: tradingKeys.events(frm, to),
    queryFn: () => {
      const p = new URLSearchParams();
      if (frm) p.set("frm", frm);
      if (to) p.set("to", to);
      const qs = p.toString();
      return api<MarketEvent[]>(`/events${qs ? `?${qs}` : ""}`);
    },
    refetchInterval: 60_000,
  });
}

export function useCreateMarketEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MarketEventIn) => api<MarketEvent>("/events", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events"] }),
  });
}

export function useDeleteMarketEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/events/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["events"] }),
  });
}
