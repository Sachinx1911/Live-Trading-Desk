"use client";

import { DataStateBadge, Dash, PanelCard } from "@/components/design";
import { useCollector } from "@/lib/api/queries";
import { formatAge, formatTime } from "@/lib/format";

export function CollectorCard() {
  const { data, isPending } = useCollector();
  const d = data?.detail ?? null;
  const running = Boolean(data?.running && d);
  const state = !running ? "disconnected" : d!.is_demo ? "demo" : d!.state === "connected" ? "live" : "disconnected";
  return (
    <PanelCard
      title="Collector"
      subtitle={running ? `provider ${d!.provider} · updated ${formatAge(d!.updated_at)} ago` : isPending ? "checking…" : "Not running"}
      actions={<DataStateBadge state={state} detail={running ? d!.state : "not running"} />}
    >
      {!running ? (
        <p className="text-[11px] text-text-3">
          No heartbeat in Redis. Start it with <code className="font-mono">make collector</code>; nothing is collected until then.
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs md:grid-cols-4">
          <dt className="text-text-3">Last message</dt>
          <dd className="tabular text-text-1">{d!.last_message_at ? formatTime(d!.last_message_at) : <Dash />}</dd>
          <dt className="text-text-3">Latency</dt>
          <dd className="tabular text-text-1">{d!.latency_ms != null ? `${Math.round(d!.latency_ms)} ms` : <Dash />}</dd>
          <dt className="text-text-3">Reconnects today</dt>
          <dd className="tabular text-text-1">{d!.reconnects_today}</dd>
          <dt className="text-text-3">Ticks</dt>
          <dd className="tabular text-text-1">{d!.builder?.ticks ?? <Dash />}</dd>
          <dt className="text-text-3">Outside session</dt>
          <dd className="tabular text-text-1">{d!.builder?.outside_session ?? <Dash />}</dd>
          <dt className="text-text-3">Tracked</dt>
          <dd className="col-span-3 truncate text-text-1">{d!.tracked.join(", ") || <Dash />}</dd>
          {d!.message && (
            <>
              <dt className="text-text-3">Note</dt>
              <dd className="col-span-3 text-text-2">{d!.message}</dd>
            </>
          )}
        </dl>
      )}
    </PanelCard>
  );
}
