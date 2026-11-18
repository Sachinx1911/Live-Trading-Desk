"use client";

import Link from "next/link";
import { DataStateBadge, PanelCard } from "@/components/design";
import { useBrokers } from "@/lib/api/queries";
import { formatTime } from "@/lib/format";

export function BrokerSessionPanel() {
  const { data } = useBrokers();
  const upstox = data?.find((b) => b.broker === "upstox");
  const valid = upstox?.status === "valid";
  return (
    <PanelCard title="Broker session" actions={<Link href="/settings/brokers" className="text-[11px] text-accent-cyan">settings</Link>}>
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-secondary">
          {!upstox || !upstox.configured ? "No broker configured" : valid ? `Upstox · ${upstox.client_code ?? ""}` : "Upstox · login required"}
        </p>
        {valid && upstox?.expires_at ? (
          <DataStateBadge state="live" detail={`until ${formatTime(upstox.expires_at)}`} />
        ) : (
          <DataStateBadge state="disconnected" detail={upstox?.configured ? "login" : "not set up"} />
        )}
      </div>
    </PanelCard>
  );
}
