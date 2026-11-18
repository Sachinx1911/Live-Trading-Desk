import { PanelCard, PhasePlaceholder } from "@/components/design";

export default function Page() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <PanelCard title="NSE" subtitle="National Stock Exchange of India">
        <dl className="grid grid-cols-2 gap-y-1 text-xs">
          <dt className="text-text-3">Timezone</dt><dd className="text-text-1">Asia/Kolkata</dd>
          <dt className="text-text-3">Regular session</dt><dd className="tabular text-text-1">09:15–15:30 IST</dd>
          <dt className="text-text-3">Intraday square-off</dt><dd className="tabular text-text-1">15:20 IST</dd>
          <dt className="text-text-3">Currency</dt><dd className="text-text-1">INR</dd>
          <dt className="text-text-3">Segments</dt><dd className="text-text-1">Equity · Index · Futures · Options</dd>
        </dl>
        <p className="mt-3 text-[11px] text-text-3">Static reference until the exchanges table is served by the API (Phase 2).</p>
      </PanelCard>
      <PanelCard title="Other exchanges" subtitle="Ships in Phase 9">
        <PhasePlaceholder phase={9} what="BSE, MCX and global market adapters" />
      </PanelCard>
    </div>
  );
}
