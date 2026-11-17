"use client";

import { Dash, EmptyState, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import { useCoverage } from "@/lib/api/queries";
import { formatDateTime, formatNumber } from "@/lib/format";

export function CoverageTable({ instrumentId }: { instrumentId?: number }) {
  const { data, isPending, isError } = useCoverage(instrumentId);
  return (
    <PanelCard title="Historical data coverage" subtitle="Rows stored per instrument × timeframe × provider" bodyClassName="p-0">
      {isPending ? (
        <Skeleton className="m-3 h-24" />
      ) : isError ? (
        <EmptyState title="Could not load coverage" className="m-3" />
      ) : !data || data.length === 0 ? (
        <EmptyState title="No candles stored yet" description="Run the collector or a backfill job." className="m-3" />
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-text-muted">
            <tr className="border-b border-border-subtle">
              <th className="px-3 py-1.5 text-left font-medium">Instrument</th>
              <th className="px-3 py-1.5 text-left font-medium">TF</th>
              <th className="px-3 py-1.5 text-left font-medium">Provider</th>
              <th className="px-3 py-1.5 text-left font-medium">First</th>
              <th className="px-3 py-1.5 text-left font-medium">Last</th>
              <th className="px-3 py-1.5 text-right font-medium">Rows</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={`${r.instrument_id}-${r.timeframe}-${r.provider}`} className="border-b border-border-subtle/60 last:border-0">
                <td className="px-3 py-1 tabular text-text-primary">#{r.instrument_id}</td>
                <td className="px-3 py-1 text-text-secondary">{r.timeframe}</td>
                <td className="px-3 py-1 text-text-secondary">{r.provider}</td>
                <td className="px-3 py-1 tabular text-text-secondary">{r.first_ts ? formatDateTime(r.first_ts) : <Dash />}</td>
                <td className="px-3 py-1 tabular text-text-secondary">{r.last_ts ? formatDateTime(r.last_ts) : <Dash />}</td>
                <td className="px-3 py-1 text-right tabular text-text-primary">{formatNumber(r.rows)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </PanelCard>
  );
}
