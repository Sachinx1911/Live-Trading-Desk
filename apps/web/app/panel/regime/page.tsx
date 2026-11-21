"use client";

import { Suspense } from "react";
import { RegimeTile } from "@/components/dashboard/RegimeTile";
import { RegimeStrip } from "@/components/market/RegimeStrip";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { useRegimeSummary } from "@/lib/api/regime";
import { formatAge } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";

/** Deterministic regime labels, read-only (recompute stays on the dashboard). */
function RegimePanel() {
  const { values, errors: paramErrors } = usePanelParams("regime");
  const symbol = values.symbol;
  const days = values.days != null ? Number(values.days) : 30;
  const errors = [...paramErrors];
  if (values.days != null && (days < 5 || days > 120)) errors.push({ param: "days", message: `${days} is outside 5-120` });
  const summary = useRegimeSummary();
  const row = symbol ? summary.data?.find((r) => r.symbol === symbol) : undefined;
  const latest = (symbol ? [row] : (summary.data ?? [])).map((r) => r?.today?.computed_at).filter(Boolean).sort().at(-1) as string | undefined;

  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="regime"
      subtitle={symbol ? `${symbol} · ${days}d` : "all tracked indices"}
      state={summary.isError ? "disconnected" : summary.isSuccess ? (latest ? "historical" : "disconnected") : undefined}
      stateDetail={latest ? `computed ${formatAge(latest)} ago` : summary.isSuccess ? "not computed" : undefined}
      fullHref={fullPageUrl("regime")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="regime" errors={errors} />);
  if (summary.isError) return frame(<PanelMessage tone="error" title="Regime service unavailable" description="The API did not answer; nothing is assumed." />);
  if (summary.isPending) return frame(<PanelMessage title="Loading regime…" />);
  if (symbol && !row)
    return frame(
      <PanelMessage
        tone="error"
        title={`symbol: no regime is computed for ${symbol}`}
        description={`The worker classifies: ${summary.data.map((r) => r.symbol).join(", ") || "nothing yet"}.`}
      />,
    );
  return frame(
    <div className="flex min-h-full flex-col bg-pane">
      {row && <RegimeStrip instrumentId={row.instrument_id} days={days} />}
      <RegimeTile bare onlySymbol={symbol} className="flex-1" />
    </div>,
  );
}

export default function RegimePanelPage() {
  return (
    <Suspense>
      <RegimePanel />
    </Suspense>
  );
}
