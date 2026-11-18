"use client";

import { EmptyState } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useImportJobs } from "@/lib/api/imports";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  succeeded: "text-up",
  completed: "text-up",
  failed: "text-down",
  running: "text-warn",
  queued: "text-text-2",
  partial: "text-warn",
};

function day(iso: string | null): string {
  return iso ? formatDateTime(iso).slice(0, 10) : "—";
}

export function ImportJobsTable() {
  const { data, isPending, error } = useImportJobs();
  if (isPending) return <Skeleton className="h-24" />;
  if (error) return <p className="text-xs text-down">Could not load import jobs.</p>;
  if (!data || data.length === 0) {
    return <EmptyState title="No imports yet" description="Committed imports appear here with their counts and range." />;
  }
  return (
    <Table dense>
      <TableHeader>
        <TableRow>
          <TableHead className="text-right">#</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Provider</TableHead>
          <TableHead>Timeframe</TableHead>
          <TableHead>Range</TableHead>
          <TableHead className="text-right">Written / read</TableHead>
          <TableHead className="text-right">Rejected</TableHead>
          <TableHead>File</TableHead>
          <TableHead>Error</TableHead>
          <TableHead>Created (IST)</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((j) => (
          <TableRow key={j.id}>
            <TableCell className="text-right tabular text-text-3">{j.id}</TableCell>
            <TableCell className={cn("font-medium", STATUS_TONE[j.status] ?? "text-text-2")}>{j.status}</TableCell>
            <TableCell className="font-mono text-[12px]">{j.provider}</TableCell>
            <TableCell className="tabular">{j.timeframe ?? "—"}</TableCell>
            <TableCell className="tabular text-text-2">
              {day(j.range_from)} → {day(j.range_to)}
            </TableCell>
            <TableCell className="text-right tabular">
              {formatNumber(j.rows_written)} / {formatNumber(j.rows_read)}
            </TableCell>
            <TableCell className={cn("text-right tabular", j.rows_rejected > 0 && "text-down")}>{formatNumber(j.rows_rejected)}</TableCell>
            <TableCell className="max-w-48 truncate text-text-2" title={j.source_uri ?? undefined}>
              {j.source_uri ?? "—"}
            </TableCell>
            <TableCell className="max-w-64 truncate text-down" title={j.error ?? undefined}>
              {j.error ?? ""}
            </TableCell>
            <TableCell className="tabular text-text-2">{formatDateTime(j.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
