"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { EmptyState, PanelCard } from "@/components/design";
import { BrokerCard } from "@/components/settings/BrokerCard";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys, useBrokers } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

const REASONS: Record<string, string> = {
  missing_params: "the broker did not return an authorization code",
  bad_state: "the login link expired or was already used (links are valid for 10 minutes)",
  account: "the account that started the login no longer exists",
  exchange: "the broker rejected the authorization code (check API key, secret and redirect URI)",
};

function LoginBanner() {
  const params = useSearchParams();
  const qc = useQueryClient();
  const login = params.get("login");
  const broker = params.get("broker") ?? "broker";
  const reason = params.get("reason");

  useEffect(() => {
    if (login) qc.invalidateQueries({ queryKey: queryKeys.brokers });
  }, [login, qc]);

  if (!login) return null;
  const ok = login === "ok";
  return (
    <div
      role={ok ? "status" : "alert"}
      className={cn(
        "rounded-sm border px-3 py-2 text-xs",
        ok
          ? "border-pnl-positive/40 bg-pnl-positive/10 text-pnl-positive"
          : "border-pnl-negative/40 bg-pnl-negative/10 text-pnl-negative",
      )}
    >
      {ok
        ? `${broker} login successful. The session is valid until ~03:30 IST tomorrow.`
        : `${broker} login failed: ${(reason && REASONS[reason]) ?? reason ?? "unknown reason"}.`}
    </div>
  );
}

function BrokersContent() {
  const { data, isPending, isError } = useBrokers();
  return (
    <div className="flex flex-col gap-3">
      <Suspense fallback={null}>
        <LoginBanner />
      </Suspense>
      <PanelCard title="Daily login" bodyClassName="text-xs text-text-secondary">
        Broker access tokens expire every day at about 03:30 IST and cannot be renewed
        automatically (broker rule). Log in before 09:00 IST on each trading day; a reminder is sent
        at 08:15 IST when the session is not valid. An expired session shows as Disconnected
        everywhere, never as stale &ldquo;live&rdquo; data.
      </PanelCard>
      {isPending && (
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      )}
      {isError && (
        <EmptyState title="Cannot load broker status" description="The API did not respond." />
      )}
      {data && (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.map((s) => (
            <BrokerCard key={s.broker} status={s} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <BrokersContent />
    </Suspense>
  );
}
