"use client";

import { Suspense, useEffect, useRef } from "react";
import { OptionChainTable } from "@/components/market/OptionChainTable";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { useInstrumentBySymbol, usePanelParams } from "@/components/panels/usePanel";
import { useChainExpiries, useOptionChain } from "@/lib/api/queries";
import { formatDateTime } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";

function OptionChainPanel() {
  const { values, errors } = usePanelParams("option-chain");
  const symbol = values.symbol;
  const greeks = values.greeks === "1";
  const inst = useInstrumentBySymbol(errors.length ? undefined : symbol);
  const id = inst.data?.instrument_id ?? null;
  const expiries = useChainExpiries(id);
  const wanted = values.expiry;
  const known = expiries.data ?? [];
  const expiry = wanted ?? known[0];
  const expiryUnknown = wanted != null && expiries.isSuccess && !known.includes(wanted);
  const expiryIso = expiry && !expiryUnknown ? `${expiry}T15:30:00+05:30` : undefined;
  const chain = useOptionChain(expiryIso ? id : null, expiryIso);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Small windows: bring the ATM strike into view once the chain is there.
  useEffect(() => {
    bodyRef.current?.querySelector("[data-atm]")?.scrollIntoView({ block: "center" });
  }, [chain.data]);

  const subtitle = symbol ? `${symbol}${expiry ? ` · exp ${expiry}` : ""}${greeks ? " · greeks" : ""}` : undefined;
  const source = chain.data ? `${chain.data.source} · ${formatDateTime(chain.data.ts)}` : undefined;
  const frame = (children: React.ReactNode, state?: Parameters<typeof PanelFrame>[0]["state"]) => (
    <PanelFrame panel="option-chain" subtitle={subtitle} state={state} source={source} fullHref={fullPageUrl("option-chain")}>
      <div ref={bodyRef} className="min-h-full">
        {children}
      </div>
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="option-chain" errors={errors} />);
  if (inst.isPending) return frame(<PanelMessage title={`Resolving ${symbol}…`} />);
  if (inst.isError) return frame(<PanelMessage tone="error" title="Cannot reach the API" />, "disconnected");
  if (!inst.data) return frame(<PanelMessage tone="error" title={`symbol: ${symbol} not found`} description="No such index in the instrument master." />);
  if (expiries.isPending) return frame(<PanelMessage title="Loading expiries…" />);
  if (expiryUnknown)
    return frame(
      <PanelMessage
        tone="error"
        title={`expiry: no snapshot stored for ${wanted}`}
        description={known.length ? `Stored expiries for ${symbol}: ${known.slice(0, 8).join(", ")}${known.length > 8 ? ", …" : ""}` : `No option-chain snapshot stored for ${symbol} yet.`}
      />,
    );
  if (!expiry)
    return frame(
      <PanelMessage title={`No option chain stored for ${symbol}`} description="The collector writes a snapshot every few minutes while the feed runs." />,
      "disconnected",
    );

  return frame(
    <OptionChainTable underlyingId={id} expiry={expiryIso} symbol={symbol} defaultGreeks={greeks} bare />,
    chain.data?.freshness ?? (chain.isPending ? undefined : "disconnected"),
  );
}

export default function OptionChainPanelPage() {
  return (
    <Suspense>
      <OptionChainPanel />
    </Suspense>
  );
}
