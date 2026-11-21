"use client";

import { Check } from "lucide-react";
import { EmptyState } from "@/components/design";
import type { AlertItem } from "@/lib/api/generated";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEV_DOT: Record<string, string> = { critical: "bg-down", warning: "bg-warn", info: "bg-accent" };
const SEV_TEXT: Record<string, string> = { critical: "text-down", warning: "text-warn", info: "text-accent-text" };

export function SeverityTag({ severity }: { severity: string }) {
  return <span className={cn("hud-label text-[10px]", SEV_TEXT[severity] ?? "text-text-3")}>{severity}</span>;
}

/** Alerts newest first. Every value shown comes from the stored alert; nothing is derived. */
export function AlertList({
  alerts,
  onAck,
  acking,
  compact = false,
  emptyTitle = "No alerts",
  emptyDescription,
}: {
  alerts: AlertItem[];
  onAck?: (id: number) => void;
  acking?: boolean;
  compact?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (alerts.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return (
    <ul className="flex flex-col divide-y divide-border">
      {alerts.map((a) => {
        const acked = a.acknowledged_at !== null;
        return (
          <li key={a.id} className={cn("flex items-start gap-2 py-2", acked && "opacity-60")}>
            <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEV_DOT[a.severity] ?? "bg-text-3")} aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[13px] font-medium text-text-1">{a.title}</span>
                <SeverityTag severity={a.severity} />
              </div>
              {!compact && <p className="text-[12px] text-text-2">{a.message}</p>}
              <p className="text-[11px] text-text-3">
                {formatDateTime(a.ts)} · {a.kind}
                {!compact && a.delivered?.telegram ? ` · telegram ${a.delivered.telegram}` : ""}
                {acked ? ` · acknowledged ${formatDateTime(a.acknowledged_at as string)}` : ""}
              </p>
            </div>
            {onAck && !acked && (
              <button
                type="button"
                onClick={() => onAck(a.id)}
                disabled={acking}
                className="inline-flex shrink-0 items-center gap-1 rounded-[var(--r-sm)] border border-border px-2 py-0.5 text-[11px] text-text-2 hover:bg-raised-hover hover:text-text-1 disabled:opacity-50"
                aria-label={`Acknowledge ${a.title}`}
              >
                <Check className="size-3" aria-hidden /> Ack
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
