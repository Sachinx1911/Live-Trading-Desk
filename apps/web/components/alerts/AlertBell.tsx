"use client";

import Link from "next/link";
import { Bell } from "lucide-react";
import { AlertList } from "@/components/alerts/AlertList";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAckAlert, useAckAll, useAlerts, useUnreadAlerts } from "@/lib/api/alerts";
import { cn } from "@/lib/utils";

/** Top-bar bell: unread (unacknowledged) count, critical in red; opens the latest unread. */
export function AlertBell() {
  const unread = useUnreadAlerts();
  const list = useAlerts(true, 10);
  const ack = useAckAlert();
  const ackAll = useAckAll();
  const n = unread.data?.unread ?? 0;
  const critical = (unread.data?.critical ?? 0) > 0;
  return (
    <Popover>
      <PopoverTrigger
        className="relative inline-flex size-7 shrink-0 items-center justify-center rounded-[var(--r-pill)] border border-border bg-raised text-text-2 hover:bg-raised-hover hover:text-text-1"
        aria-label={unread.isError ? "Alerts (count unavailable)" : `Alerts, ${n} unread`}
        title={unread.isError ? "Alerts: API not reachable" : `${n} unread alert(s)`}
      >
        <Bell className="size-3.5" aria-hidden />
        {n > 0 && (
          <span
            className={cn(
              "absolute -right-1 -top-1 min-w-4 rounded-full px-1 text-center font-mono text-[10px] leading-4 text-white",
              critical ? "bg-down" : "bg-warn",
            )}
          >
            {n > 99 ? "99+" : n}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="hud-label text-amber">Alerts</span>
          <div className="flex items-center gap-3 text-[12px]">
            {n > 0 && (
              <button type="button" className="text-text-2 hover:text-text-1" onClick={() => ackAll.mutate()} disabled={ackAll.isPending}>
                Acknowledge all
              </button>
            )}
            <Link href="/alerts" className="text-accent-text hover:underline">
              All alerts
            </Link>
          </div>
        </div>
        <div className="max-h-96 overflow-y-auto px-3">
          {list.isError ? (
            <p className="py-4 text-[12px] text-down">Cannot reach the API.</p>
          ) : (
            <AlertList
              compact
              alerts={list.data ?? []}
              onAck={(id) => ack.mutate(id)}
              acking={ack.isPending}
              emptyTitle={list.isPending ? "Loading…" : "Nothing unread"}
            />
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
