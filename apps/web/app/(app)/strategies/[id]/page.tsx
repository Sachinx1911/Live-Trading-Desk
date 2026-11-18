"use client";

import { ArrowRightLeft, BarChart3, Pencil, Play, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { EmptyState, PanelCard } from "@/components/design";
import { DslEditor } from "@/components/strategies/DslEditor";
import { DslViewer } from "@/components/strategies/DslViewer";
import { ValidationReportView } from "@/components/strategies/ValidationReportView";
import { RunStrategySheet } from "@/components/trading/RunStrategySheet";
import { StatusChip } from "@/components/trading/StatusChip";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/lib/api/client";
import type { StrategyVersionStatus } from "@/lib/api/generated";
import { useCreateVersion, useEditVersion, useStrategy, useStrategyVersion, useStrategyVersions, useTransitionVersion } from "@/lib/api/trading";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const TRANSITIONS: Record<StrategyVersionStatus, StrategyVersionStatus[]> = {
  draft: ["backtested", "rejected"],
  backtested: ["validated", "paper", "rejected"],
  validated: ["paper", "rejected"],
  paper: ["approved_live", "retired"],
  approved_live: ["retired"],
  retired: [],
  rejected: [],
};

const EMPTY_DSL = {
  dsl_schema_version: "1.0",
  name: "",
  market: "NSE",
  timeframe: "5m",
  universe: { kind: "instrument", instrument_ids: [] },
  session: { product: "INTRADAY", square_off_at: "15:15", no_new_entries_after: "14:45" },
  indicators: {},
  entry: null,
  exit: null,
  stop_loss: null,
  target: null,
  position_sizing: { method: "fixed_lots", lots: 1 },
};

function TransitionBox({ versionId, status }: { versionId: number; status: StrategyVersionStatus }) {
  const tr = useTransitionVersion();
  const [to, setTo] = useState<StrategyVersionStatus | "">("");
  const [note, setNote] = useState("");
  const targets = TRANSITIONS[status];
  const err = tr.error instanceof ApiRequestError ? tr.error.message : null;
  if (targets.length === 0) return <p className="text-[11px] text-text-3">Terminal status.</p>;
  return (
    <form
      className="flex flex-wrap items-center gap-2 text-xs"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!to) return;
        await tr.mutateAsync({ versionId, to_status: to, note: note || null });
        setTo("");
        setNote("");
      }}
    >
      <ArrowRightLeft className="size-3.5 text-text-3" />
      <select value={to} onChange={(e) => setTo(e.target.value as StrategyVersionStatus)} className="h-7 border border-border bg-raised px-2 text-xs" aria-label="Transition to">
        <option value="">Move to…</option>
        {targets.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
      </select>
      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (evidence, reason)" className="h-7 w-64 text-xs" />
      <Button type="submit" size="xs" variant={to === "approved_live" ? "destructive" : "outline"} disabled={!to || tr.isPending}>
        {to === "approved_live" ? "Approve for LIVE (owner)" : "Apply"}
      </Button>
      {err && <span className="text-down">{err}</span>}
    </form>
  );
}

export default function StrategyDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data: strategy, isPending } = useStrategy(Number.isFinite(id) ? id : null);
  const { data: versions } = useStrategyVersions(Number.isFinite(id) ? id : null);
  const [selected, setSelected] = useState<number | null>(null);
  const selId = selected ?? versions?.[versions.length - 1]?.id ?? null;
  const { data: version } = useStrategyVersion(selId);
  const [editing, setEditing] = useState(false);
  const create = useCreateVersion(id);
  const edit = useEditVersion();
  const { accountId } = usePaperAccount();

  if (isPending) return <Skeleton className="h-64" />;
  if (!strategy) return <EmptyState title="Strategy not found" />;

  return (
    <div className="grid grid-cols-12 gap-3">
      <PanelCard title={strategy.name} subtitle={`${strategy.category.replace("_", " ")} · ${strategy.origin.replace("_", " ")} · ${strategy.description ?? ""}`} className="col-span-12 xl:col-span-4" bodyClassName="p-0">
        {!versions || versions.length === 0 ? (
          <div className="p-3">
            <EmptyState title="No version yet" description="Add the first draft by pasting a DSL document." />
            <Button size="sm" className="mt-2" onClick={() => setEditing(true)}><Pencil /> Add first version</Button>
          </div>
        ) : (
          <ul>
            {versions.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  onClick={() => { setSelected(v.id); setEditing(false); }}
                  className={cn("flex w-full flex-col gap-0.5 border-b border-border/60 px-3 py-2 text-left hover:bg-raised/60", selId === v.id && "bg-raised")}
                >
                  <span className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-text-1">v{v.version_no}</span>
                    <StatusChip value={v.status} />
                  </span>
                  <span className="text-[11px] text-text-3">{formatDateTime(v.created_at)} · {v.created_by}{v.parent_version_id ? ` · from #${v.parent_version_id}` : ""}</span>
                  {v.change_summary && <span className="text-[11px] text-text-2">{v.change_summary}</span>}
                </button>
              </li>
            ))}
            <li className="p-2">
              <Button size="xs" variant="ghost" onClick={() => { setSelected(null); setEditing(true); }}><Pencil /> New version from scratch</Button>
            </li>
          </ul>
        )}
      </PanelCard>

      <PanelCard
        title={version ? `Version ${version.version_no}` : editing ? "New version" : "Version"}
        subtitle={version ? `hash ${version.dsl_hash.slice(0, 12)} · schema ${version.dsl_schema_version}${version.frozen_at ? ` · frozen ${formatDateTime(version.frozen_at)}` : " · editable draft (clone on edit)"}` : undefined}
        className="col-span-12 xl:col-span-8"
        actions={
          version && !editing ? (
            <>
              {accountId != null && ["draft", "backtested", "validated", "paper"].includes(version.status) && (
                <RunStrategySheet accountId={accountId} presetStrategyId={strategy.id} trigger={<Button size="xs" variant="outline"><Play /> Run on paper</Button>} />
              )}
              <Link href={`/backtesting?strategy=${strategy.id}`} className="inline-flex h-6 items-center gap-1 rounded-sm border border-border px-2 text-[11px] text-accent-cyan hover:bg-raised"><BarChart3 className="size-3" /> Backtest</Link>
              <Link href={`/strategies/new/visual?from=${version.id}`} className="inline-flex h-6 items-center gap-1 rounded-sm border border-border px-2 text-[11px] text-accent-cyan hover:bg-raised"><SlidersHorizontal className="size-3" /> Edit visually</Link>
              <Button size="xs" variant="outline" onClick={() => setEditing(true)}><Pencil /> Edit as new version</Button>
            </>
          ) : undefined
        }
      >
        {editing ? (
          <DslEditor
            initial={version?.dsl ?? EMPTY_DSL}
            saving={create.isPending || edit.isPending}
            onSave={async (dsl, summary) => {
              const v = version && selected != null
                ? await edit.mutateAsync({ versionId: version.id, dsl, change_summary: summary || null })
                : await create.mutateAsync({ dsl, change_summary: summary || null });
              setSelected(v.id);
              setEditing(false);
            }}
          />
        ) : version ? (
          <div className="flex flex-col gap-3">
            <ValidationReportView report={version.validation} />
            <DslViewer dsl={version.dsl} />
            {version.source_text && (
              <div className="rounded-sm border border-ai/30 bg-ai/5 p-2 text-[11px] text-text-2">
                <span className="text-ai">Original description ({version.source_language ?? "?"}):</span> {version.source_text}
              </div>
            )}
            <TransitionBox versionId={version.id} status={version.status} />
          </div>
        ) : (
          <EmptyState title="Select a version" />
        )}
      </PanelCard>
    </div>
  );
}
