"use client";

import { StatusChip } from "@/components/trading/StatusChip";
import type { JobStatus } from "@/lib/api/generated";
import { cn } from "@/lib/utils";

const TONE: Record<JobStatus, "ok" | "warn" | "bad" | "muted" | "info"> = {
  queued: "muted",
  running: "info",
  succeeded: "ok",
  failed: "bad",
  cancelled: "muted",
  partial: "warn",
};

export function JobStatusChip({ status }: { status: JobStatus }) {
  return <StatusChip value={status} tone={TONE[status]} />;
}

export function ProgressBar({ pct, className }: { pct: number; className?: string }) {
  const p = Math.max(0, Math.min(100, pct));
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-sm bg-raised", className)} role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-accent-cyan transition-[width]" style={{ width: `${p}%` }} />
    </div>
  );
}
