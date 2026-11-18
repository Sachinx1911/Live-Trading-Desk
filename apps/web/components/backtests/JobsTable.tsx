"use client";

import { Ban, ExternalLink } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isLive, useCancelBacktest } from "@/lib/api/backtests";
import type { BacktestJob } from "@/lib/api/generated";
import { formatDateTime } from "@/lib/format";
import { JobStatusChip, ProgressBar } from "./JobStatus";

function day(iso: string) {
  return new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "2-digit" }).format(new Date(iso));
}

export function JobsTable({ jobs, isPending }: { jobs: BacktestJob[] | undefined; isPending?: boolean }) {
  const cancel = useCancelBacktest();
  if (isPending) return <Skeleton className="h-24" />;
  if (!jobs || jobs.length === 0) return <EmptyState title="No backtests yet" description="Configure one on the left and run it." />;
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-3">
        <tr className="border-b border-border">
          <th className="px-2 py-1.5 text-left font-medium">Job</th>
          <th className="px-2 py-1.5 text-left font-medium">Version</th>
          <th className="px-2 py-1.5 text-left font-medium">Instrument</th>
          <th className="px-2 py-1.5 text-left font-medium">Range</th>
          <th className="px-2 py-1.5 text-left font-medium">TF</th>
          <th className="px-2 py-1.5 text-left font-medium">Status</th>
          <th className="px-2 py-1.5 text-left font-medium">Queued</th>
          <th className="px-2 py-1.5 text-right font-medium"></th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => (
          <tr key={j.id} className="border-b border-border/60">
            <td className="px-2 py-1.5">
              <Link href={`/backtesting/${j.id}`} className="text-text-1 hover:text-accent-cyan">
                #{j.id}{j.label ? ` · ${j.label}` : ""}
              </Link>
            </td>
            <td className="px-2 py-1.5 tabular text-text-2">v#{j.strategy_version_id}</td>
            <td className="px-2 py-1.5 tabular text-text-2">#{j.instrument_id}</td>
            <td className="px-2 py-1.5 tabular text-text-2">{day(j.start_at)} → {day(j.end_at)}</td>
            <td className="px-2 py-1.5 text-text-2">{j.timeframe}</td>
            <td className="px-2 py-1.5">
              <div className="flex flex-col gap-1">
                <JobStatusChip status={j.status} />
                {j.status === "running" && <ProgressBar pct={j.progress_pct} className="w-24" />}
                {j.error && <span className="max-w-48 truncate text-[10px] text-down" title={j.error}>{j.error}</span>}
              </div>
            </td>
            <td className="px-2 py-1.5 tabular text-text-2">{formatDateTime(j.queued_at)}</td>
            <td className="px-2 py-1.5 text-right">
              <div className="flex justify-end gap-1">
                {isLive(j.status) && (
                  <Button size="xs" variant="ghost" onClick={() => cancel.mutate(j.id)} aria-label="Cancel"><Ban /> cancel</Button>
                )}
                <Link href={`/backtesting/${j.id}`} className="inline-flex h-6 items-center gap-1 rounded-sm px-1.5 text-[11px] text-accent-cyan hover:bg-raised"><ExternalLink className="size-3" /> open</Link>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
