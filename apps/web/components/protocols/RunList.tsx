"use client";

import { OpenAsPanel } from "@/components/panels/OpenAsPanel";
import { EmptyState } from "@/components/design";
import { Button } from "@/components/ui/button";
import type { ProtocolRun, ProtocolRunStep } from "@/lib/api/generated";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const RUN_STYLE: Record<string, string> = {
  succeeded: "text-up",
  partial: "text-warn",
  failed: "text-down",
  cancelled: "text-text-3",
  running: "text-accent-text",
  awaiting_confirmation: "text-amber",
};
const STEP_STYLE: Record<string, string> = {
  succeeded: "text-up",
  failed: "text-down",
  skipped: "text-text-3",
  running: "text-accent-text",
  pending: "text-text-3",
};

function StepRow({ s, i }: { s: ProtocolRunStep; i: number }) {
  const summary = typeof s.result?.summary === "string" ? s.result.summary : null;
  return (
    <li className="rounded-[var(--r-sm)] border border-border px-2 py-1.5">
      <div className="flex flex-wrap items-baseline gap-2 text-[12px]">
        <span className="font-mono text-text-3">{i + 1}.</span>
        <span className="font-mono text-text-1">{s.tool}</span>
        <span className={cn("hud-label text-[10px]", STEP_STYLE[s.status])}>{s.status}</span>
        {s.on_error === "continue" && <span className="text-[10px] text-text-3">continue on error</span>}
      </div>
      {summary && <p className="mt-0.5 text-[12px] text-text-2">{summary}</p>}
      {s.error && <p className="mt-0.5 text-[12px] text-down">{s.error}</p>}
      {s.result && (
        <details className="mt-1">
          <summary className="cursor-pointer text-[11px] text-text-3 hover:text-text-2">stored result</summary>
          <pre className="mt-1 max-h-72 overflow-auto rounded-[var(--r-sm)] bg-raised p-2 font-mono text-[11px] text-text-2">
            {JSON.stringify(s.result, null, 2)}
          </pre>
        </details>
      )}
    </li>
  );
}

export function RunList({
  runs,
  isOwner,
  onConfirm,
  onCancel,
  busy,
  readOnly = false,
}: {
  runs: ProtocolRun[];
  isOwner: boolean;
  onConfirm: (id: number) => void;
  onCancel: (id: number) => void;
  busy: boolean;
  /** Panels: no confirm / cancel buttons; those stay on /protocols. */
  readOnly?: boolean;
}) {
  if (runs.length === 0) return <EmptyState title="No runs yet" description="Run a protocol to see each step's stored result here." />;
  return (
    <ul className="flex flex-col gap-2">
      {runs.map((r) => {
        const open = r.status === "running" || r.status === "awaiting_confirmation";
        return (
          <li key={r.id} className={cn("rounded-[var(--r-sm)] border border-border p-2", r.status === "awaiting_confirmation" && "border-amber/60")}>
            <details open={open}>
              <summary className="flex cursor-pointer flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-mono text-[11px] text-text-3">#{r.id}</span>
                <span className="text-[13px] font-medium text-text-1">{r.protocol_name}</span>
                <span className="font-mono text-[11px] text-text-3">v{r.protocol_version}</span>
                <span className={cn("hud-label text-[10px]", RUN_STYLE[r.status])}>{r.status.replace("_", " ")}</span>
                <span className="text-[11px] text-text-3">
                  {formatDateTime(r.started_at)}
                  {r.finished_at ? ` → ${formatDateTime(r.finished_at)}` : ""} · {r.trigger}
                </span>
                {!readOnly && <OpenAsPanel panel="protocol-run" params={{ id: r.id }} className="ml-auto self-center" />}
              </summary>
              {r.status === "awaiting_confirmation" && (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-[var(--r-sm)] border border-amber/40 bg-amber/5 p-2 text-[12px]">
                  <span className="text-text-2">
                    This protocol asks first. It will run: {r.steps.map((s) => s.tool).join(" → ")}.
                  </span>
                  {readOnly ? (
                    <span className="text-text-3">Confirm or cancel it on the Protocols page.</span>
                  ) : (
                    <>
                      {isOwner ? (
                        <Button size="sm" onClick={() => onConfirm(r.id)} disabled={busy}>
                          Confirm and run
                        </Button>
                      ) : (
                        <span className="text-text-3">Only the owner can confirm.</span>
                      )}
                      <Button size="sm" variant="ghost" onClick={() => onCancel(r.id)} disabled={busy}>
                        Cancel
                      </Button>
                    </>
                  )}
                </div>
              )}
              {r.status === "running" && (
                <div className="mt-2 flex items-center gap-2 text-[12px] text-text-3">
                  Running in the worker…
                  {!readOnly && (
                    <Button size="sm" variant="ghost" onClick={() => onCancel(r.id)} disabled={busy}>
                      Cancel remaining steps
                    </Button>
                  )}
                </div>
              )}
              {r.summary && <p className="mt-2 text-[12px] text-text-2">{r.summary}</p>}
              <ol className="mt-2 flex flex-col gap-1">
                {r.steps.map((s, i) => (
                  <StepRow key={i} s={s} i={i} />
                ))}
              </ol>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
