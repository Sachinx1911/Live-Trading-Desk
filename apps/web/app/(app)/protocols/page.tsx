"use client";

import { Play } from "lucide-react";
import { EmptyState, PanelCard } from "@/components/design";
import { ProtocolEditor } from "@/components/protocols/ProtocolEditor";
import { RiskBadge } from "@/components/protocols/RiskBadge";
import { RunList } from "@/components/protocols/RunList";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api/client";
import { useMe } from "@/lib/api/queries";
import {
  useCancelRun,
  useConfirmRun,
  useProtocolActions,
  useProtocolRuns,
  useProtocols,
  useRunProtocol,
} from "@/lib/api/protocols";

/*
 * Protocols (Mark 1 Stage 3.1): named, fixed bundles of registered actions (plan §2.4).
 * Runs execute in the worker; each step's stored result is shown as returned. No action can
 * place an order; "Shutdown" asks first, "Clean Slate" engages the kill switch at once.
 */
function errText(e: unknown): string | null {
  if (!e) return null;
  return e instanceof ApiRequestError ? e.message : "Cannot reach the API.";
}

export default function ProtocolsPage() {
  const protocols = useProtocols();
  const actions = useProtocolActions();
  const runs = useProtocolRuns(30);
  const run = useRunProtocol();
  const confirm = useConfirmRun();
  const cancel = useCancelRun();
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const busy = confirm.isPending || cancel.isPending;
  const runErr = errText(run.error) ?? errText(confirm.error) ?? errText(cancel.error);

  return (
    <div className="flex flex-col gap-3">
      <PanelCard title="Protocols" subtitle="One button, a fixed list of actions. Green reads, yellow changes paper state, red needs owner confirmation.">
        {protocols.isError ? (
          <p className="text-[12px] text-down">{errText(protocols.error)}</p>
        ) : protocols.isPending ? (
          <p className="text-[12px] text-text-3">Loading…</p>
        ) : (protocols.data ?? []).length === 0 ? (
          <EmptyState title="No protocols" />
        ) : (
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {protocols.data!.map((p) => (
              <div key={p.code} className="flex flex-col gap-2 rounded-[var(--r-sm)] border border-border p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-[14px] font-medium text-text-1">{p.name}</span>
                      <span className="font-mono text-[11px] text-text-3">
                        {p.code} · v{p.version}
                      </span>
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] uppercase text-text-3">
                      <span>{p.is_builtin ? "built-in" : "owner"}</span>
                      {p.confirm_required && <span className="text-amber">asks first</span>}
                    </div>
                  </div>
                  <Button size="sm" onClick={() => run.mutate(p.code)} disabled={run.isPending} aria-label={`Run ${p.name}`}>
                    <Play className="size-3.5" aria-hidden /> Run
                  </Button>
                </div>
                {p.description && <p className="text-[12px] text-text-2">{p.description}</p>}
                <ol className="flex flex-col gap-1">
                  {p.steps.map((s, i) => (
                    <li key={i} className="flex items-center gap-2 text-[12px]">
                      <span className="font-mono text-text-3">{i + 1}.</span>
                      <span className="font-mono text-text-1">{s.tool}</span>
                      <RiskBadge risk={s.risk} />
                      {s.on_error === "continue" && <span className="text-[10px] text-text-3">continue on error</span>}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        )}
        {runErr && <p className="mt-2 text-[12px] text-down">{runErr}</p>}
      </PanelCard>

      <PanelCard title="Runs" subtitle="Newest first. Results are what each action stored; missing data is reported, never filled in.">
        {runs.isError ? (
          <p className="text-[12px] text-down">{errText(runs.error)}</p>
        ) : runs.isPending ? (
          <p className="text-[12px] text-text-3">Loading…</p>
        ) : (
          <RunList runs={runs.data ?? []} isOwner={isOwner} onConfirm={(id) => confirm.mutate(id)} onCancel={(id) => cancel.mutate(id)} busy={busy} />
        )}
      </PanelCard>

      {isOwner && (
        <PanelCard title="Owner protocols" subtitle="JSON steps only, checked against the action catalogue. Each save is a new version.">
          {actions.data && protocols.data ? (
            <ProtocolEditor protocols={protocols.data} actions={actions.data} />
          ) : (
            <p className="text-[12px] text-text-3">{actions.isError ? errText(actions.error) : "Loading…"}</p>
          )}
        </PanelCard>
      )}
    </div>
  );
}
