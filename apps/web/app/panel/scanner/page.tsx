"use client";

import { Suspense, useMemo, useState } from "react";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { ScannerTable } from "@/components/scanner/ScannerTable";
import { ApiRequestError } from "@/lib/api/client";
import type { ScanSort } from "@/lib/api/generated";
import { useRunScan, useSavedScans, useScannerFields, useScannerPresets } from "@/lib/api/scanner";
import { formatNumber } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";

const LIMIT = 200;

/** Result of one preset or saved scan over the EOD snapshot. Sorting is a local view change. */
function ScannerPanel() {
  const { values, errors } = usePanelParams("scanner");
  const scanId = values.preset != null ? Number(values.preset) : null;
  const fields = useScannerFields();
  const presets = useScannerPresets();
  const saved = useSavedScans();
  const scan = useMemo(() => [...(presets.data ?? []), ...(saved.data ?? [])].find((s) => s.id === scanId) ?? null, [presets.data, saved.data, scanId]);
  const [sortOverride, setSortOverride] = useState<ScanSort | null | undefined>(undefined);
  const sort = sortOverride === undefined ? (scan?.sort ?? null) : sortOverride;
  const req = useMemo(
    () => ({ filters: scan?.filters ?? { all: [], any: [] }, sort, columns: scan?.columns ?? null, offset: 0, limit: LIMIT }),
    [scan, sort],
  );
  const run = useRunScan(req, !!scan && fields.isSuccess);
  const noSnapshot = run.error instanceof ApiRequestError && run.error.status === 404;
  const fieldMap = useMemo(() => new Map((fields.data?.fields ?? []).map((f) => [f.name, f])), [fields.data]);
  const listsLoaded = presets.isSuccess && saved.isSuccess;

  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="scanner"
      subtitle={scan ? `${scan.name}${run.data ? ` · ${formatNumber(run.data.total, 0)} match${run.data.total === 1 ? "" : "es"}` : ""}` : values.preset ? `scan #${values.preset}` : undefined}
      state={run.data ? "historical" : run.isError ? "disconnected" : undefined}
      stateDetail={run.data ? `EOD ${run.data.as_of}` : noSnapshot ? "no snapshot" : undefined}
      source={run.data?.provider}
      fullHref={scan ? `/scanner?scan=${scan.id}` : fullPageUrl("scanner")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="scanner" errors={errors} />);
  if (presets.isError || saved.isError || fields.isError) return frame(<PanelMessage tone="error" title="Cannot reach the scanner API" />);
  if (!listsLoaded) return frame(<PanelMessage title="Loading scans…" />);
  if (!scan)
    return frame(
      <PanelMessage
        tone="error"
        title={`preset: no preset or saved scan with id ${scanId}`}
        description={`Known: ${[...presets.data, ...saved.data].map((s) => `${s.id} ${s.name}`).join(" · ") || "none"}`}
      />,
    );
  if (noSnapshot) return frame(<PanelMessage title="No scanner snapshot yet" description="The worker builds it nightly from EOD candles; the owner can recompute it on the Scanner page." />);
  if (run.isError) return frame(<PanelMessage tone="error" title="Scan failed" description={run.error.message} />);
  if (run.isPending) return frame(<PanelMessage title="Running scan…" />);

  return frame(
    <>
      <ScannerTable columns={run.data.columns} rows={run.data.rows} fields={fieldMap} sort={sort} onSort={setSortOverride} loading={run.isFetching} linkRows={false} />
      {run.data.total > run.data.rows.length && (
        <p className="border-t border-border px-3 py-1.5 text-[11px] text-text-3">
          Showing the first {run.data.rows.length} of {formatNumber(run.data.total, 0)}; the full list is on the Scanner page.
        </p>
      )}
    </>,
  );
}

export default function ScannerPanelPage() {
  return (
    <Suspense>
      <ScannerPanel />
    </Suspense>
  );
}
