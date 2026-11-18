"use client";

import { ChevronLeft, ChevronRight, Save } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";
import { EmptyState, PanelCard } from "@/components/design";
import { ColumnTabs } from "@/components/scanner/ColumnTabs";
import { FilterChips } from "@/components/scanner/FilterChips";
import { COLUMN_SETS, EMPTY_FILTERS, columnSetFor, sameScan } from "@/components/scanner/lib";
import { PresetPills } from "@/components/scanner/PresetPills";
import { SaveScanDialog } from "@/components/scanner/SaveScanDialog";
import { ScannerTable } from "@/components/scanner/ScannerTable";
import { SnapshotPill } from "@/components/scanner/SnapshotPill";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/lib/api/client";
import type { SavedScan, ScanFilters, ScanSort } from "@/lib/api/generated";
import { useMe } from "@/lib/api/queries";
import { useRequestSnapshot, useRunScan, useSavedScans, useScanSnapshot, useScannerFields, useScannerPresets } from "@/lib/api/scanner";
import { formatNumber } from "@/lib/format";

const PAGE = 100;

interface ScanState {
  scan: number | null; // active preset / saved scan id
  filters: ScanFilters;
  sort: ScanSort | null;
  columns: string[];
  page: number;
  /** True when the link only named a scan id: its definition is applied once the lists load. */
  fromScan: boolean;
}

/** URL ↔ state. Filters travel as JSON in `f`, so a scan is a shareable link. */
function parse(p: URLSearchParams, defaults: string[]): ScanState {
  let filters = EMPTY_FILTERS;
  try {
    const raw = p.get("f");
    if (raw) {
      const j = JSON.parse(raw) as Partial<ScanFilters>;
      filters = { all: Array.isArray(j.all) ? j.all : [], any: Array.isArray(j.any) ? j.any : [] };
    }
  } catch {
    /* ignore malformed link */
  }
  const s = p.get("sort");
  const sort = s?.includes(":") ? ({ field: s.split(":")[0], dir: s.split(":")[1] === "asc" ? "asc" : "desc" } as ScanSort) : null;
  const set = p.get("set");
  const cols = p.get("cols");
  const columns = cols ? cols.split(",").filter(Boolean) : set && COLUMN_SETS[set] ? COLUMN_SETS[set].columns : defaults;
  const scan = p.get("scan");
  const fromScan = scan != null && !p.get("f") && !p.get("cols") && !p.get("set") && !p.get("sort");
  return { scan: scan ? Number(scan) : null, filters, sort, columns, page: Math.max(0, Number(p.get("page") ?? 0) || 0), fromScan };
}

function serialize(s: ScanState, defaults: string[]): string {
  const p = new URLSearchParams();
  if (s.scan != null) p.set("scan", String(s.scan));
  if (s.filters.all.length || s.filters.any.length) p.set("f", JSON.stringify(s.filters));
  if (s.sort) p.set("sort", `${s.sort.field}:${s.sort.dir}`);
  const set = columnSetFor(s.columns);
  if (set !== "custom") {
    if (set !== "overview" || s.columns.join() !== defaults.join()) p.set("set", set);
  } else p.set("cols", s.columns.join(","));
  if (s.page > 0) p.set("page", String(s.page));
  return p.toString();
}

function ScannerPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fieldsQ = useScannerFields();
  const presetsQ = useScannerPresets();
  const savedQ = useSavedScans();
  const snapshotQ = useScanSnapshot();
  const me = useMe();
  const recompute = useRequestSnapshot();
  const isOwner = me.data?.roles.includes("owner") ?? false;

  const defaults = fieldsQ.data?.default_columns ?? COLUMN_SETS.overview.columns;
  const [raw, setState] = useState<ScanState>(() => parse(params, defaults));
  const [saveOpen, setSaveOpen] = useState(false);

  const update = useCallback(
    (patch: Partial<ScanState>, resetPage = true) => {
      setState((prev) => {
        const next = { ...prev, ...patch, fromScan: false, page: resetPage && patch.page == null ? 0 : (patch.page ?? prev.page) };
        const qs = serialize(next, defaults);
        router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
        return next;
      });
    },
    [router, pathname, defaults],
  );

  // Opening `/scanner?scan=3` applies the scan's definition once the lists arrive (derived, not an effect).
  const presets = useMemo(() => presetsQ.data ?? [], [presetsQ.data]);
  const saved = useMemo(() => savedQ.data ?? [], [savedQ.data]);
  const active = useMemo(() => [...presets, ...saved].find((s) => s.id === raw.scan) ?? null, [presets, saved, raw.scan]);
  const state: ScanState = raw.fromScan && active ? { ...raw, filters: active.filters, sort: active.sort ?? null, columns: active.columns } : raw;

  const fieldMap = useMemo(() => new Map((fieldsQ.data?.fields ?? []).map((f) => [f.name, f])), [fieldsQ.data]);
  const req = useMemo(
    () => ({ filters: state.filters, sort: state.sort, columns: state.columns, offset: state.page * PAGE, limit: PAGE }),
    [state.filters, state.sort, state.columns, state.page],
  );
  const run = useRunScan(req, fieldsQ.isSuccess);
  const noSnapshot = run.error instanceof ApiRequestError && run.error.status === 404;
  const runErr = run.error instanceof ApiRequestError && !noSnapshot ? run.error.message : null;
  const total = run.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const dirty = active ? !sameScan({ filters: state.filters, sort: state.sort, columns: state.columns }, active) : state.filters.all.length + state.filters.any.length > 0;

  const pickScan = (s: SavedScan | null) =>
    update(s ? { scan: s.id, filters: s.filters, sort: s.sort ?? null, columns: s.columns } : { scan: null, filters: EMPTY_FILTERS, sort: null, columns: defaults });

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title="Market Scanner"
        subtitle="Rule-based scans over the end-of-day snapshot. Click a row to open it on the chart."
        actions={
          <div className="flex items-center gap-2">
            <SnapshotPill info={snapshotQ.data} isOwner={isOwner} busy={recompute.isPending} onRecompute={() => recompute.mutate(undefined)} />
            <Button variant={dirty ? "primary" : "outline"} size="sm" onClick={() => setSaveOpen(true)} disabled={!fieldsQ.isSuccess}>
              <Save className="size-3" /> {active && !active.is_preset ? (dirty ? "Update scan" : "Edit scan") : "Save scan"}
            </Button>
          </div>
        }
        bodyClassName="flex flex-col gap-3"
      >
        {presetsQ.isPending ? (
          <Skeleton className="h-7 w-full" />
        ) : (
          <PresetPills presets={presets} saved={saved} activeId={state.scan} onPick={pickScan} />
        )}
        {fieldsQ.isPending ? (
          <Skeleton className="h-[34px] w-2/3" />
        ) : fieldsQ.isError ? (
          <div className="text-[12px] text-down">Could not load the scanner field catalogue.</div>
        ) : (
          <FilterChips fields={fieldsQ.data.fields} filters={state.filters} onChange={(f) => update({ filters: f })} />
        )}
      </PanelCard>

      <PanelCard
        className="min-h-96"
        bodyClassName="flex flex-col"
        banner={
          recompute.isSuccess ? (
            <span className="text-[12px] text-text-2">Recompute queued in the worker; the table refreshes when the snapshot lands.</span>
          ) : undefined
        }
      >
        <ColumnTabs
          active={columnSetFor(state.columns)}
          columns={state.columns}
          fields={fieldsQ.data?.fields ?? []}
          onSet={(id) => update({ columns: id === "custom" ? state.columns : COLUMN_SETS[id].columns }, false)}
          onColumns={(cols) => update({ columns: cols }, false)}
        />
        {noSnapshot ? (
          <EmptyState
            title="No snapshot yet"
            description={isOwner ? "Press Recompute to build today's snapshot from EOD candles." : "The owner has to run Recompute once; the worker also builds it nightly."}
            className="my-6"
          />
        ) : runErr ? (
          <div className="p-4 text-[12px] text-down">{runErr}</div>
        ) : run.isPending ? (
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <ScannerTable
            columns={run.data?.columns ?? state.columns}
            rows={run.data?.rows ?? []}
            fields={fieldMap}
            sort={state.sort}
            onSort={(s) => update({ sort: s })}
            loading={run.isFetching}
          />
        )}
        {run.data && total > 0 && (
          <div className="flex items-center justify-between border-t border-border px-5 py-2 text-[12px] text-text-3">
            <span>
              {formatNumber(total, 0)} instrument{total === 1 ? "" : "s"} · EOD {run.data.as_of} · {run.data.provider.toUpperCase()}
            </span>
            {pages > 1 && (
              <span className="inline-flex items-center gap-1">
                <Button variant="ghost" size="icon-xs" disabled={state.page === 0} onClick={() => update({ page: state.page - 1 }, false)} aria-label="Previous page">
                  <ChevronLeft className="size-3.5" />
                </Button>
                <span className="tabular">
                  {state.page + 1} / {pages}
                </span>
                <Button variant="ghost" size="icon-xs" disabled={state.page + 1 >= pages} onClick={() => update({ page: state.page + 1 }, false)} aria-label="Next page">
                  <ChevronRight className="size-3.5" />
                </Button>
              </span>
            )}
          </div>
        )}
      </PanelCard>

      {saveOpen && (
        <SaveScanDialog
          open={saveOpen}
          onOpenChange={setSaveOpen}
          current={{ filters: state.filters, sort: state.sort, columns: state.columns }}
          base={active}
          onSaved={(s) => update({ scan: s.id }, false)}
          onDeleted={() => update({ scan: null }, false)}
        />
      )}
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <ScannerPage />
    </Suspense>
  );
}
