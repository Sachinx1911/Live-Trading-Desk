"use client";

import { RefreshCw } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import type { ScanSnapshotInfo } from "@/lib/api/generated";
import { formatAge, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Wall clock that ticks once a minute, so the age colour does not depend on render timing. */
function subscribeMinute(cb: () => void) {
  const id = setInterval(cb, 60_000);
  return () => clearInterval(id);
}
function useNow(): number {
  return useSyncExternalStore(subscribeMinute, () => Math.floor(Date.now() / 60_000) * 60_000, () => 0);
}

/** Data-state pill for the scan snapshot (CLAUDE.md rule 5: every number shows its source and freshness). */
export function SnapshotPill({
  info,
  isOwner,
  onRecompute,
  busy,
}: {
  info: ScanSnapshotInfo | undefined;
  isOwner: boolean;
  onRecompute: () => void;
  busy: boolean;
}) {
  const now = useNow();
  const computed = info?.computed_at ? new Date(info.computed_at) : null;
  const ageH = computed && now ? (now - computed.getTime()) / 3_600_000 : null;
  // Daily snapshot: green within a trading day, amber up to 3 days (weekend), red beyond; grey when none.
  const tone = ageH == null ? "border-border bg-raised text-text-3" : ageH < 26 ? "border-up/40 bg-up/10 text-up" : ageH < 80 ? "border-warn/40 bg-warn/10 text-warn" : "border-down/40 bg-down/10 text-down";
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn("inline-flex h-7 items-center gap-1.5 rounded-[var(--r-pill)] border px-2.5 text-[12px] font-medium whitespace-nowrap", tone)}
        title={computed ? `Computed ${formatDateTime(computed)} from ${info?.provider} EOD candles · ${info?.instrument_count} instruments` : "No snapshot computed yet"}
      >
        <span className={cn("size-1.5 rounded-full", ageH == null ? "bg-text-3" : "bg-current")} />
        {info?.as_of ? `EOD ${info.as_of}` : "No snapshot"}
        {computed && now > 0 && <span className="font-normal opacity-80">· {formatAge(computed, new Date(now))}</span>}
        {info?.provider && <span className="font-normal uppercase opacity-70">· {info.provider}</span>}
      </span>
      {isOwner && (
        <Button variant="outline" size="sm" onClick={onRecompute} disabled={busy} title="Recompute today's snapshot in the worker">
          <RefreshCw className={cn("size-3", busy && "animate-spin")} /> Recompute
        </Button>
      )}
    </div>
  );
}
