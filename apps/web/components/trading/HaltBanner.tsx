"use client";

import { AlertOctagon, ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { Activation } from "@/lib/api/generated";
import { useKillSwitch } from "@/lib/api/trading";

/** Shown on paper pages when trading is halted by the kill switch or a loss limit. */
export function HaltBanner({ accountId, activations }: { accountId: number | null; activations?: Activation[] }) {
  const { data } = useKillSwitch(accountId ?? undefined);
  const active = (data ?? []).filter((k) => k.active);
  const lossHits = (activations ?? []).filter((a) => a.stop_reason?.toLowerCase().includes("loss limit"));
  if (active.length === 0 && lossHits.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 rounded-md border border-down/50 bg-down/10 px-3 py-2 text-xs">
      {active.map((k) => (
        <p key={k.scope} className="flex items-center gap-2 text-down">
          <AlertOctagon className="size-3.5" /> Kill switch active ({k.scope})
          {k.detail?.reason && <span className="text-text-2">— {k.detail.reason}</span>}
          <Link href="/trading" className="ml-auto underline">
            Manage
          </Link>
        </p>
      ))}
      {lossHits.map((a) => (
        <p key={a.id} className="flex items-center gap-2 text-warn">
          <ShieldAlert className="size-3.5" /> {a.strategy_name} v{a.version_no} paused: {a.stop_reason}
        </p>
      ))}
    </div>
  );
}
