"use client";

import { DataStateBadge, EmptyState, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConnectionState, Freshness, ProviderStatus } from "@/lib/api/generated";
import { useProviders } from "@/lib/api/queries";
import { formatAge } from "@/lib/format";

function toFreshness(p: ProviderStatus): Freshness {
  if (p.is_demo) return "demo";
  const map: Record<ConnectionState, Freshness> = {
    connected: "live",
    connecting: "delayed",
    disconnected: "disconnected",
    auth_required: "disconnected",
    error: "disconnected",
  };
  return map[p.state];
}

const STATE_TEXT: Record<ConnectionState, string> = {
  connected: "Connected",
  connecting: "Connecting",
  disconnected: "Disconnected",
  auth_required: "Login required",
  error: "Error",
};

export function ProviderStatusPanel() {
  const { data, isPending, isError, error } = useProviders();

  return (
    <PanelCard title="Data providers" subtitle="Reported by the API; nothing here is assumed">
      {isPending && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}
      {isError && (
        <div className="flex flex-col gap-2">
          <DataStateBadge state="disconnected" detail="API unreachable" />
          <p className="text-[11px] text-text-3">{error instanceof Error ? error.message : "Request failed"}</p>
        </div>
      )}
      {data && data.length === 0 && (
        <EmptyState title="No provider configured" description="Set DEFAULT_MARKET_DATA_PROVIDER and connect a provider in Settings." />
      )}
      {data && data.length > 0 && (
        <ul className="flex flex-col divide-y divide-border-subtle">
          {data.map((p) => (
            <li key={p.code} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-text-1">{p.display_name}</p>
                <p className="truncate text-[11px] text-text-3">
                  {STATE_TEXT[p.state]}
                  {p.last_message_at ? ` · last message ${formatAge(p.last_message_at)} ago` : " · no messages yet"}
                  {p.message ? ` · ${p.message}` : ""}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {p.latency_ms != null && (
                  <span className="tabular text-[11px] text-text-2">{Math.round(p.latency_ms)} ms</span>
                )}
                <DataStateBadge state={toFreshness(p)} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </PanelCard>
  );
}
