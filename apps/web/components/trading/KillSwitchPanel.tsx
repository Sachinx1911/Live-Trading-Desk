"use client";

import { AlertOctagon, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/lib/api/client";
import type { KillSwitchScope } from "@/lib/api/generated";
import { useMe } from "@/lib/api/queries";
import { useActivateKill, useClearKill, useKillSwitch, useKillSwitchEvents } from "@/lib/api/trading";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function errText(e: unknown): string | null {
  if (!e) return null;
  return e instanceof ApiRequestError ? e.message : "Cannot reach the API.";
}

export function KillSwitchPanel({ accountId }: { accountId: number | null }) {
  const { data: statuses } = useKillSwitch(accountId ?? undefined);
  const { data: events } = useKillSwitchEvents();
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const activate = useActivateKill();
  const clear = useClearKill();
  const [scope, setScope] = useState<KillSwitchScope>("global");
  const [reason, setReason] = useState("");
  const [flatten, setFlatten] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const [clearReason, setClearReason] = useState("");

  const anyActive = (statuses ?? []).some((s) => s.active);
  const scopeId = scope === "account" ? (accountId ?? undefined) : undefined;

  return (
    <PanelCard
      title="Kill switch"
      subtitle="Stops all new entries immediately. Anyone can activate; only the owner can clear."
      className={cn(anyActive && "border-down/60")}
      actions={anyActive ? <span className="text-[11px] font-semibold text-down">ACTIVE</span> : <span className="flex items-center gap-1 text-[11px] text-up"><ShieldCheck className="size-3.5" /> armed, inactive</span>}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <ul className="flex flex-col gap-1 text-xs">
            {(statuses ?? []).map((s) => (
              <li key={s.scope} className="flex items-center justify-between rounded-sm border border-border px-2 py-1.5">
                <span className="text-text-1">{s.scope}</span>
                {s.active ? (
                  <span className="text-down">ON {s.detail?.reason ? `· ${s.detail.reason}` : ""} {s.detail?.by ? `· ${s.detail.by}` : ""}</span>
                ) : (
                  <span className="text-text-3">off</span>
                )}
              </li>
            ))}
          </ul>
          <form
            className="flex flex-col gap-2 rounded-sm border border-down/40 bg-down/5 p-3"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!confirm) {
                setConfirm(true);
                return;
              }
              await activate.mutateAsync({ scope, scopeId, reason: reason.trim(), flatten });
              setConfirm(false);
              setReason("");
            }}
          >
            <div className="flex items-center gap-2 text-xs">
              <label className="text-text-2" htmlFor="ks-scope">Scope</label>
              <select id="ks-scope" value={scope} onChange={(e) => setScope(e.target.value as KillSwitchScope)} className="h-7 border border-border bg-raised px-2 text-xs">
                <option value="global">Global (everything)</option>
                <option value="account" disabled={accountId == null}>Paper account {accountId ? `#${accountId}` : ""}</option>
              </select>
              <label className="ml-auto flex items-center gap-1 text-text-2">
                <input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} /> square off positions
              </label>
            </div>
            <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required, goes to the audit log)" className="h-8 text-xs" />
            <Button type="submit" variant="destructive" size="lg" disabled={activate.isPending || reason.trim().length < 3} className="font-semibold">
              <AlertOctagon /> {confirm ? "CONFIRM: activate kill switch" : "Activate kill switch"}
            </Button>
            {confirm && (
              <Button type="button" size="xs" variant="ghost" onClick={() => setConfirm(false)}>
                cancel
              </Button>
            )}
            {errText(activate.error) && <p className="text-[11px] text-down">{errText(activate.error)}</p>}
          </form>
          {anyActive && (
            <form
              className="flex items-center gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                for (const s of (statuses ?? []).filter((x) => x.active)) {
                  const [kind, id] = s.scope.split(":");
                  await clear.mutateAsync({ scope: kind as KillSwitchScope, scopeId: id ? Number(id) : undefined, reason: clearReason.trim() });
                }
                setClearReason("");
              }}
            >
              <Input required minLength={3} value={clearReason} onChange={(e) => setClearReason(e.target.value)} placeholder={isOwner ? "Reason for clearing" : "Owner role required to clear"} disabled={!isOwner} className="h-8 text-xs" />
              <Button type="submit" variant="outline" size="sm" disabled={!isOwner || clear.isPending || clearReason.trim().length < 3}>
                Clear
              </Button>
              {errText(clear.error) && <p className="text-[11px] text-down">{errText(clear.error)}</p>}
            </form>
          )}
        </div>
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-text-3">Event log</p>
          {!events || events.length === 0 ? (
            <EmptyState title="No kill switch events" />
          ) : (
            <table className="w-full text-[11px]">
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id} className="border-b border-border/60">
                    <td className="py-1 tabular text-text-3">{formatDateTime(ev.ts)}</td>
                    <td className={cn("py-1 font-semibold uppercase", ev.action === "activate" ? "text-down" : "text-up")}>{ev.action}</td>
                    <td className="py-1 text-text-2">{ev.scope}{ev.scope_id != null ? `:${ev.scope_id}` : ""}</td>
                    <td className="py-1 text-text-2">{ev.reason}{ev.positions_flattened ? " · flatten" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </PanelCard>
  );
}
