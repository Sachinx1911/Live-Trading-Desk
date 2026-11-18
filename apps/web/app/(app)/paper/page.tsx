"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { DataStateBadge, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ActivationsTable } from "@/components/trading/ActivationsTable";
import { HaltBanner } from "@/components/trading/HaltBanner";
import { KpiTiles } from "@/components/trading/KpiTiles";
import { PaperHeader } from "@/components/trading/PaperHeader";
import { RunStrategySheet } from "@/components/trading/RunStrategySheet";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { ApiRequestError } from "@/lib/api/client";
import { useActivations, useResetPaperAccount } from "@/lib/api/trading";
import { formatDateTime } from "@/lib/format";

function ResetBox({ accountId }: { accountId: number }) {
  const reset = useResetPaperAccount(accountId);
  const [cap, setCap] = useState("");
  const [open, setOpen] = useState(false);
  const err = reset.error instanceof ApiRequestError ? reset.error.message : null;
  if (!open) {
    return (
      <Button size="xs" variant="ghost" onClick={() => setOpen(true)}>
        <RotateCcw /> Reset account
      </Button>
    );
  }
  return (
    <form
      className="flex items-center gap-2 text-xs"
      onSubmit={async (e) => {
        e.preventDefault();
        const n = Number(cap);
        await reset.mutateAsync({ initial_capital: n > 0 ? n : null });
        setOpen(false);
      }}
    >
      <Input type="number" placeholder="new capital (optional)" value={cap} onChange={(e) => setCap(e.target.value)} className="h-7 w-44 text-xs" />
      <Button type="submit" size="xs" variant="destructive" disabled={reset.isPending}>Confirm reset</Button>
      <Button type="button" size="xs" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      {err && <span className="text-down">{err}</span>}
    </form>
  );
}

function Overview({ accountId }: { accountId: number }) {
  const { account } = usePaperAccount();
  const { data: activations } = useActivations(accountId, true);
  if (!account) return null;
  const running = activations?.filter((a) => a.status !== "stopped");
  return (
    <>
      <HaltBanner accountId={accountId} activations={activations} />
      <KpiTiles account={account} />
      <PanelCard
        title="Active strategies"
        subtitle={account.reset_at ? `Account reset ${formatDateTime(account.reset_at)}` : `Created ${formatDateTime(account.created_at)}`}
        actions={
          <>
            <ResetBox accountId={accountId} />
            <RunStrategySheet accountId={accountId} />
          </>
        }
        bodyClassName="p-0"
      >
        <ActivationsTable activations={running} />
      </PanelCard>
      {activations && activations.some((a) => a.status === "stopped") && (
        <PanelCard title="Stopped" bodyClassName="p-0" actions={<DataStateBadge state="historical" />}>
          <ActivationsTable activations={activations.filter((a) => a.status === "stopped")} />
        </PanelCard>
      )}
    </>
  );
}

export default function PaperPage() {
  return <PaperHeader>{(id) => <Overview accountId={id} />}</PaperHeader>;
}
