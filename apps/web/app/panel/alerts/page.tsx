"use client";

import { Suspense } from "react";
import { AlertList } from "@/components/alerts/AlertList";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { useAlerts, useUnreadAlerts } from "@/lib/api/alerts";
import { fullPageUrl } from "@/lib/panels";

/** Alerts feed, read-only: acknowledging stays on /alerts. */
function AlertsPanel() {
  const { values, errors: paramErrors } = usePanelParams("alerts");
  const unreadOnly = values.unread === "1";
  const limit = values.limit != null ? Number(values.limit) : 100;
  const errors = [...paramErrors];
  if (values.limit != null && (limit < 1 || limit > 300)) errors.push({ param: "limit", message: `${limit} is outside 1-300` });
  const alerts = useAlerts(unreadOnly, errors.length ? 1 : limit);
  const unread = useUnreadAlerts();

  const subtitle = unread.data ? `${unread.data.unread} unread · ${unread.data.critical} critical${unreadOnly ? " · unread only" : ""}` : undefined;
  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="alerts"
      subtitle={subtitle}
      state={alerts.isSuccess ? "historical" : alerts.isError ? "disconnected" : undefined}
      stateDetail={alerts.isSuccess ? "stored" : undefined}
      fullHref={fullPageUrl("alerts")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="alerts" errors={errors} />);
  if (alerts.isError) return frame(<PanelMessage tone="error" title="Cannot reach the API" description="Alerts are unavailable; nothing is shown in their place." />);
  if (alerts.isPending) return frame(<PanelMessage title="Loading alerts…" />);
  return frame(
    <div className="px-3">
      <AlertList
        alerts={alerts.data}
        emptyTitle={unreadOnly ? "Nothing unread" : "No alerts stored yet"}
        emptyDescription="Alerts are evaluated every minute 09:00–15:45 IST on trading days; signals and owner-rule blocks come from the paper trader."
      />
    </div>,
  );
}

export default function AlertsPanelPage() {
  return (
    <Suspense>
      <AlertsPanel />
    </Suspense>
  );
}
