"use client";

import { Pause, Play, Square } from "lucide-react";
import { Fragment, useState } from "react";
import { EmptyState } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Activation } from "@/lib/api/generated";
import { useStopActivation, useToggleActivation } from "@/lib/api/trading";
import { formatDateTime } from "@/lib/format";
import { StatusChip } from "./StatusChip";

function StopRow({ a, onClose }: { a: Activation; onClose: () => void }) {
  const stop = useStopActivation();
  const [reason, setReason] = useState("stopped by user");
  const [flatten, setFlatten] = useState(true);
  return (
    <tr className="border-b border-border/60 bg-raised/60">
      <td colSpan={6} className="px-3 py-2">
        <form
          className="flex flex-wrap items-center gap-2 text-xs"
          onSubmit={async (e) => {
            e.preventDefault();
            await stop.mutateAsync({ id: a.id, reason: reason.trim() || "stopped by user", flatten });
            onClose();
          }}
        >
          <span className="text-text-2">Stop {a.strategy_name} v{a.version_no}:</span>
          <Input value={reason} onChange={(e) => setReason(e.target.value)} className="h-7 w-64 text-xs" aria-label="Stop reason" />
          <label className="flex items-center gap-1 text-text-2">
            <input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} /> square off open position
          </label>
          <Button type="submit" size="xs" variant="destructive" disabled={stop.isPending}>
            Confirm stop
          </Button>
          <Button type="button" size="xs" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </form>
      </td>
    </tr>
  );
}

export function ActivationsTable({ activations }: { activations: Activation[] | undefined }) {
  const toggle = useToggleActivation();
  const [stopping, setStopping] = useState<number | null>(null);
  if (!activations || activations.length === 0) {
    return <EmptyState title="No strategy running" description="Use “Run a strategy” to activate a version on this account." />;
  }
  return (
    <table className="w-full text-xs">
      <thead className="text-[10px] uppercase tracking-wide text-text-3">
        <tr className="border-b border-border">
          <th className="px-3 py-1.5 text-left font-medium">Strategy</th>
          <th className="px-3 py-1.5 text-left font-medium">Version</th>
          <th className="px-3 py-1.5 text-left font-medium">Instrument</th>
          <th className="px-3 py-1.5 text-left font-medium">Status</th>
          <th className="px-3 py-1.5 text-left font-medium">Since</th>
          <th className="px-3 py-1.5 text-right font-medium">Actions</th>
        </tr>
      </thead>
      <tbody>
        {activations.map((a) => (
          <Fragment key={a.id}>
            <tr className="border-b border-border/60">
              <td className="px-3 py-1.5 text-text-1">{a.strategy_name}</td>
              <td className="px-3 py-1.5 tabular text-text-2">v{a.version_no}</td>
              <td className="px-3 py-1.5 text-text-1">{a.symbol ?? `#${a.instrument_id}`}</td>
              <td className="px-3 py-1.5">
                <StatusChip value={a.status} />
                {a.stop_reason && <span className="ml-2 text-[11px] text-text-3">{a.stop_reason}</span>}
              </td>
              <td className="px-3 py-1.5 tabular text-text-2">{formatDateTime(a.activated_at)}</td>
              <td className="px-3 py-1.5 text-right">
                {a.status !== "stopped" && (
                  <div className="inline-flex gap-1">
                    <Button size="xs" variant="outline" onClick={() => toggle.mutate(a.id)} disabled={toggle.isPending} aria-label={a.status === "active" ? "Pause" : "Resume"}>
                      {a.status === "active" ? <Pause /> : <Play />}
                      {a.status === "active" ? "Pause" : "Resume"}
                    </Button>
                    <Button size="xs" variant="destructive" onClick={() => setStopping(a.id)} aria-label="Stop">
                      <Square /> Stop
                    </Button>
                  </div>
                )}
              </td>
            </tr>
            {stopping === a.id && <StopRow a={a} onClose={() => setStopping(null)} />}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}
