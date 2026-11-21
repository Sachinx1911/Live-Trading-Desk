"use client";

import { BreadthTile } from "@/components/dashboard/BreadthTile";
import { PanelFrame } from "@/components/panels/PanelFrame";
import { BreadthHistory } from "@/components/scanner/BreadthHistory";
import { useBreadthLatest } from "@/lib/api/breadth";
import { fullPageUrl } from "@/lib/panels";

/** NIFTY 50 breadth: latest stored session and history. End-of-day data, never live. */
export default function BreadthPanelPage() {
  const { data, isError, isSuccess } = useBreadthLatest();
  return (
    <PanelFrame
      panel="breadth"
      subtitle={data ? `NIFTY 50 · EOD ${data.as_of_date}` : "NIFTY 50"}
      state={isError ? "disconnected" : isSuccess ? (data ? "historical" : "disconnected") : undefined}
      stateDetail={data ? `EOD ${data.as_of_date}` : isSuccess ? "none stored" : undefined}
      source={data?.provider}
      fullHref={fullPageUrl("breadth")}
    >
      <div className="grid min-h-full grid-cols-1 gap-px bg-border lg:grid-cols-2">
        <BreadthTile bare />
        <BreadthHistory bare />
      </div>
    </PanelFrame>
  );
}
