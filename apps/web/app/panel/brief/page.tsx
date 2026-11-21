"use client";

import { Suspense } from "react";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { EveningBriefBody } from "@/components/reports/EveningBrief";
import { ApiRequestError } from "@/lib/api/client";
import { useDailyReport } from "@/lib/api/reports";
import { formatDateTime } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";

/** Stored evening brief (no AI). Regenerating stays on /reports. */
function BriefPanel() {
  const { values, errors } = usePanelParams("brief");
  const date = values.date ?? null;
  const report = useDailyReport(errors.length ? "invalid" : date);
  const notFound = report.error instanceof ApiRequestError && report.error.status === 404;
  const r = report.data;

  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="brief"
      subtitle={r ? `${r.content.date}${r.content.is_trading_day ? "" : " · market closed"}` : (date ?? "latest")}
      state={r ? "historical" : report.isError && !notFound ? "disconnected" : undefined}
      stateDetail={r ? `generated ${formatDateTime(r.created_at)}` : undefined}
      source={r?.content.provider}
      fullHref={fullPageUrl("brief")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="brief" errors={errors} />);
  if (report.isPending) return frame(<PanelMessage title="Loading brief…" />);
  if (notFound)
    return frame(
      <PanelMessage
        title={date ? `date: no brief stored for ${date}` : "No brief stored yet"}
        description="A brief is generated after each session at 19:00 IST; it can be regenerated on the Reports page."
      />,
    );
  if (report.isError || !r) return frame(<PanelMessage tone="error" title="Cannot reach the API" />);
  return frame(
    <div className="p-2">
      <EveningBriefBody c={r.content} />
    </div>,
  );
}

export default function BriefPanelPage() {
  return (
    <Suspense>
      <BriefPanel />
    </Suspense>
  );
}
