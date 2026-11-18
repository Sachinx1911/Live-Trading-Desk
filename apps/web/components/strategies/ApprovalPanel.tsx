"use client";

/**
 * Approval workflow for one strategy version (ADR-009: approvals are user acts).
 *
 * Shows the evidence the server already holds (succeeded backtests, paper activations),
 * the transitions that are allowed right now with the reason for every blocked one, and
 * the full approval log. Nothing here is computed on the client; the server's
 * `/readiness` decides what is allowed and the transition endpoint re-checks it.
 */
import { AlertTriangle, Ban, CheckCircle2, ChevronRight, History, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { StatusChip } from "@/components/trading/StatusChip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/lib/api/client";
import type { StrategyVersionStatus, VersionReadiness } from "@/lib/api/generated";
import { useMe } from "@/lib/api/queries";
import { useTransitionVersion, useVersionApprovals, useVersionReadiness } from "@/lib/api/trading";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const ORDER: StrategyVersionStatus[] = ["draft", "backtested", "validated", "paper", "approved_live"];

const LABEL: Record<StrategyVersionStatus, string> = {
  draft: "Draft",
  backtested: "Mark backtested",
  validated: "Mark validated",
  paper: "Promote to paper",
  approved_live: "Approve for LIVE",
  retired: "Retire",
  rejected: "Reject",
};

const HINT: Record<StrategyVersionStatus, string> = {
  draft: "",
  backtested: "At least one succeeded backtest of this exact version.",
  validated: "You reviewed the backtest and the assumptions hold.",
  paper: "Run it on a paper account; the engine is the same as the backtest.",
  approved_live: "Owner only. Opens the live gate for this version; the kill switch and risk engine still apply.",
  retired: "Stops this version for good. A reason is recorded.",
  rejected: "Marks the version rejected. A reason is recorded.",
};

function Pipeline({ status }: { status: StrategyVersionStatus }) {
  const idx = ORDER.indexOf(status);
  const terminal = status === "rejected" || status === "retired";
  return (
    <ol className="flex flex-wrap items-center gap-1 text-[11px]">
      {ORDER.map((s, i) => (
        <li key={s} className="flex items-center gap-1">
          <span
            className={cn(
              "rounded-sm border px-1.5 py-0.5",
              i < idx && !terminal && "border-up/40 bg-up/10 text-up",
              i === idx && !terminal && "border-accent bg-accent/10 text-accent",
              (i > idx || terminal) && "border-border text-text-3",
            )}
          >
            {s.replace("_", " ")}
          </span>
          {i < ORDER.length - 1 && <ChevronRight className="size-3 text-text-3" />}
        </li>
      ))}
      {terminal && (
        <li>
          <StatusChip value={status} />
        </li>
      )}
    </ol>
  );
}

function Evidence({ r }: { r: VersionReadiness }) {
  return (
    <div className="grid gap-2 text-[11px] md:grid-cols-2">
      <div className="border border-border bg-pane p-2">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-medium text-text-1">Backtests (succeeded)</span>
          <span className="tabular text-text-2">{r.backtests_succeeded}</span>
        </div>
        {r.backtests.length === 0 ? (
          <p className="text-text-3">None yet for this version.</p>
        ) : (
          <table className="w-full">
            <thead className="text-text-3">
              <tr>
                <th className="text-left font-normal">Job</th>
                <th className="text-left font-normal">TF</th>
                <th className="text-right font-normal">Trades</th>
                <th className="text-right font-normal">Return</th>
                <th className="text-right font-normal">Max DD</th>
                <th className="text-right font-normal">PF</th>
              </tr>
            </thead>
            <tbody>
              {r.backtests.slice(0, 5).map((b) => (
                <tr key={b.job_id} className="border-t border-border/60">
                  <td>
                    <Link href={`/backtesting?job=${b.job_id}`} className="text-accent-cyan hover:underline">
                      #{b.job_id}
                    </Link>
                  </td>
                  <td>{b.timeframe}</td>
                  <td className="tabular text-right">{b.trades ?? "—"}</td>
                  <td className={cn("tabular text-right", (b.total_return_pct ?? 0) >= 0 ? "text-up" : "text-down")}>
                    {b.total_return_pct == null ? "—" : `${formatNumber(b.total_return_pct, 2)}%`}
                  </td>
                  <td className="tabular text-right text-down">{b.max_drawdown_pct == null ? "—" : `${formatNumber(b.max_drawdown_pct, 2)}%`}</td>
                  <td className="tabular text-right">{b.profit_factor == null ? "—" : formatNumber(b.profit_factor, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="border border-border bg-pane p-2">
        <div className="mb-1 font-medium text-text-1">Paper / live activations</div>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          <dt className="text-text-3">Paper runs</dt>
          <dd className="tabular">{r.paper_activations} ({r.paper_active} active)</dd>
          <dt className="text-text-3">Live activations</dt>
          <dd className="tabular">{r.live_activations}</dd>
        </dl>
        <p className="mt-2 text-text-3">
          Live approval needs at least one paper run of this version. Live trading itself stays off until <code>LIVE_TRADING_ENABLED</code> is true and all five gates pass.
        </p>
      </div>
    </div>
  );
}

function ActionForm({ versionId, target, onDone, onCancel }: { versionId: number; target: StrategyVersionStatus; onDone: () => void; onCancel: () => void }) {
  const tr = useTransitionVersion();
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState("");
  const dangerous = target === "approved_live" || target === "rejected" || target === "retired";
  const needsNote = dangerous;
  const needsConfirm = target === "approved_live";
  const ok = (!needsNote || note.trim().length > 0) && (!needsConfirm || confirm === "LIVE");
  const err = tr.error instanceof ApiRequestError ? tr.error.message : tr.error ? String(tr.error) : null;
  return (
    <form
      className={cn("flex flex-col gap-2 border p-2 text-xs", target === "approved_live" ? "border-down/50 bg-down/5" : "border-border bg-pane")}
      onSubmit={async (e) => {
        e.preventDefault();
        if (!ok) return;
        await tr.mutateAsync({ versionId, to_status: target, note: note.trim() || null });
        onDone();
      }}
    >
      <div className="flex items-center gap-2">
        {target === "approved_live" ? <ShieldCheck className="size-3.5 text-down" /> : dangerous ? <Ban className="size-3.5 text-warn" /> : <CheckCircle2 className="size-3.5 text-accent" />}
        <span className="font-medium text-text-1">{LABEL[target]}</span>
        <span className="text-text-3">{HINT[target]}</span>
      </div>
      <Input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={needsNote ? "Reason / approval note (required)" : "Note (optional)"}
        className="h-7 text-xs"
        aria-label="Note"
      />
      {needsConfirm && (
        <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder='Type LIVE to confirm' className="h-7 w-48 text-xs" aria-label="Confirmation" />
      )}
      <div className="flex items-center gap-2">
        <Button type="submit" size="xs" variant={target === "approved_live" ? "destructive" : "default"} disabled={!ok || tr.isPending}>
          {tr.isPending ? "Applying…" : LABEL[target]}
        </Button>
        <Button type="button" size="xs" variant="ghost" onClick={onCancel}>Cancel</Button>
        {err && <span className="text-down">{err}</span>}
      </div>
    </form>
  );
}

export function ApprovalPanel({ versionId, status }: { versionId: number; status: StrategyVersionStatus }) {
  const { data: me } = useMe();
  const { data: r, isPending } = useVersionReadiness(versionId);
  const { data: log } = useVersionApprovals(versionId);
  const [target, setTarget] = useState<StrategyVersionStatus | null>(null);
  const isOwner = me?.roles.includes("owner") ?? false;
  if (isPending || !r) return <Skeleton className="h-24" />;
  const reachable: StrategyVersionStatus[] = [...r.allowed, ...(Object.keys(r.blockers) as StrategyVersionStatus[])];
  const forward = reachable.filter((t) => t !== "rejected" && t !== "retired");
  const backward = reachable.filter((t) => t === "rejected" || t === "retired");

  return (
    <section className="flex flex-col gap-3" aria-label="Approval workflow">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pipeline status={status} />
        <span className="text-[11px] text-text-3">Transitions are recorded with who, when, note and evidence.</span>
      </div>
      <Evidence r={r} />
      {reachable.length === 0 ? (
        <p className="text-[11px] text-text-3">Terminal status. Create a new version to continue.</p>
      ) : target ? (
        <ActionForm versionId={versionId} target={target} onDone={() => setTarget(null)} onCancel={() => setTarget(null)} />
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {forward.map((t) => {
            const blocked = r.blockers[t];
            const ownerBlocked = t === "approved_live" && !isOwner;
            return (
              <div key={t} className="flex items-center gap-1">
                <Button
                  size="xs"
                  variant={t === "approved_live" ? "destructive" : "outline"}
                  disabled={!!blocked || ownerBlocked}
                  onClick={() => setTarget(t)}
                  title={blocked?.join("; ") ?? (ownerBlocked ? "only the owner can approve for live" : HINT[t])}
                >
                  {LABEL[t]}
                </Button>
                {(blocked || ownerBlocked) && (
                  <span className="flex items-center gap-1 text-[11px] text-warn">
                    <AlertTriangle className="size-3" /> {blocked?.[0] ?? "owner only"}
                  </span>
                )}
              </div>
            );
          })}
          <span className="grow" />
          {backward.map((t) => (
            <Button key={t} size="xs" variant="ghost" className="text-text-2" onClick={() => setTarget(t)}>
              {LABEL[t]}
            </Button>
          ))}
        </div>
      )}
      <div>
        <div className="mb-1 flex items-center gap-1 text-[11px] font-medium text-text-2">
          <History className="size-3" /> Approval log
        </div>
        {!log || log.length === 0 ? (
          <p className="text-[11px] text-text-3">No transitions yet.</p>
        ) : (
          <ol className="divide-y divide-border/60 border border-border text-[11px]">
            {log.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2 px-2 py-1">
                <span className="tabular text-text-3">{formatDateTime(a.ts)}</span>
                <StatusChip value={a.from_status} />
                <ChevronRight className="size-3 text-text-3" />
                <StatusChip value={a.to_status} />
                <span className={cn("rounded-sm border px-1", a.decision === "approved" ? "border-up/40 text-up" : "border-down/40 text-down")}>{a.decision}</span>
                <span className="text-text-2">{a.user_email}</span>
                {a.note && <span className="text-text-1">“{a.note}”</span>}
                {Array.isArray(a.evidence.backtest_job_ids) && (a.evidence.backtest_job_ids as number[]).length > 0 && (
                  <span className="text-text-3">backtests {(a.evidence.backtest_job_ids as number[]).map((j) => `#${j}`).join(", ")}</span>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
