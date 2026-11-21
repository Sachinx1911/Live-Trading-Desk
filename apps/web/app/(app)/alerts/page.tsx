"use client";

import { useState } from "react";
import { OpenAsPanel } from "@/components/panels/OpenAsPanel";
import { AlertList } from "@/components/alerts/AlertList";
import { PanelCard } from "@/components/design";
import { useAckAlert, useAckAll, useAlerts, useUnreadAlerts } from "@/lib/api/alerts";
import { cn } from "@/lib/utils";

/*
 * Alerts (Mark 1 Stage 3.2): stored by the worker's minute job during market hours
 * (PCR near the pcr_guard limits, feed stale, broker session, daily loss near, kill switch,
 * trader down) and by the paper trader (signal fired, owner-rule block).
 */
export default function AlertsPage() {
  const [unackOnly, setUnackOnly] = useState(false);
  const alerts = useAlerts(unackOnly, 300);
  const unread = useUnreadAlerts();
  const ack = useAckAlert();
  const ackAll = useAckAll();
  const n = unread.data?.unread ?? 0;

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title="Alerts"
        subtitle={unread.data ? `${n} unread · ${unread.data.critical} critical` : undefined}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex rounded-[var(--r-sm)] border border-border">
              {[
                { v: false, label: "All" },
                { v: true, label: "Unread" },
              ].map((o) => (
                <button
                  key={o.label}
                  type="button"
                  onClick={() => setUnackOnly(o.v)}
                  className={cn("hud-label px-3 py-1", unackOnly === o.v ? "bg-accent-soft text-accent-text" : "text-text-3 hover:text-text-2")}
                >
                  {o.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              disabled={n === 0 || ackAll.isPending}
              onClick={() => ackAll.mutate()}
              className="rounded-[var(--r-sm)] border border-border px-2 py-1 text-[12px] text-text-2 hover:bg-raised-hover disabled:opacity-40"
            >
              Acknowledge all
            </button>
            <OpenAsPanel panel="alerts" params={{ unread: unackOnly }} />
          </div>
        }
      >
        {alerts.isError ? (
          <p className="text-[12px] text-down">Cannot reach the API.</p>
        ) : alerts.isPending ? (
          <p className="text-[12px] text-text-3">Loading…</p>
        ) : (
          <AlertList
            alerts={alerts.data ?? []}
            onAck={(id) => ack.mutate(id)}
            acking={ack.isPending}
            emptyTitle={unackOnly ? "Nothing unread" : "No alerts stored yet"}
            emptyDescription="Alerts are evaluated every minute 09:00–15:45 IST on trading days; signals and owner-rule blocks come from the paper trader."
          />
        )}
      </PanelCard>
    </div>
  );
}
