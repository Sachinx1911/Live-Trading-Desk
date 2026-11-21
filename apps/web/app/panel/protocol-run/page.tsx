"use client";

import { useQuery } from "@tanstack/react-query";
import { Suspense } from "react";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { RunList } from "@/components/protocols/RunList";
import { api, ApiRequestError } from "@/lib/api/client";
import type { ProtocolRun } from "@/lib/api/generated";
import { fullPageUrl } from "@/lib/panels";

const OPEN = new Set(["running", "awaiting_confirmation"]);

/** One protocol run with each step's stored result. Read-only: confirm / cancel stay on /protocols. */
function ProtocolRunPanel() {
  const { values, errors } = usePanelParams("protocol-run");
  const id = errors.length || values.id == null ? null : Number(values.id);
  const run = useQuery({
    queryKey: ["protocols", "runs", "one", id],
    queryFn: () => api<ProtocolRun>(`/protocols/runs/${id}`),
    enabled: id != null,
    refetchInterval: (q) => (q.state.data && OPEN.has(q.state.data.status) ? 1_500 : 30_000),
    retry: (count, err) => !(err instanceof ApiRequestError && err.status === 404) && count < 1,
  });
  const r = run.data;

  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="protocol-run"
      subtitle={r ? `#${r.id} · ${r.protocol_name} · ${r.status.replace("_", " ")}` : values.id ? `#${values.id}` : undefined}
      state={r ? "historical" : run.isError ? "disconnected" : undefined}
      stateDetail={r ? (OPEN.has(r.status) ? "refreshing" : "stored") : undefined}
      fullHref={fullPageUrl("protocol-run")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="protocol-run" errors={errors} />);
  if (run.isPending) return frame(<PanelMessage title="Loading run…" />);
  if (run.error instanceof ApiRequestError && run.error.status === 404) return frame(<PanelMessage tone="error" title={`id: protocol run #${id} not found`} />);
  if (run.isError || !r) return frame(<PanelMessage tone="error" title="Cannot reach the API" />);
  return frame(
    <div className="p-2">
      <RunList runs={[r]} isOwner={false} onConfirm={() => undefined} onCancel={() => undefined} busy={false} readOnly />
    </div>,
  );
}

export default function ProtocolRunPanelPage() {
  return (
    <Suspense>
      <ProtocolRunPanel />
    </Suspense>
  );
}
