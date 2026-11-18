"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { InstrumentSearch, instrumentLabel } from "@/components/market/InstrumentSearch";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ApiRequestError } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { useActivateStrategy, useStrategies, useStrategyVersions } from "@/lib/api/trading";
import { StatusChip } from "./StatusChip";

const PAPER_OK = new Set(["draft", "backtested", "validated", "paper"]);

export function RunStrategySheet({ accountId, presetStrategyId, trigger }: { accountId: number; presetStrategyId?: number; trigger?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const { data: strategies } = useStrategies(false);
  const [strategyId, setStrategyId] = useState<number | null>(presetStrategyId ?? null);
  const { data: versions } = useStrategyVersions(strategyId);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [instrument, setInstrument] = useState<Instrument | null>(null);
  const activate = useActivateStrategy(accountId);
  const err = activate.error instanceof ApiRequestError ? activate.error.message : activate.error ? "Cannot reach the API." : null;

  const eligible = (versions ?? []).filter((v) => PAPER_OK.has(v.status));
  const chosenVersion = versionId ?? eligible[eligible.length - 1]?.id ?? null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={(trigger as React.ReactElement) ?? <Button size="sm"><Play /> Run a strategy</Button>} />
      <SheetContent side="right" className="w-[420px] bg-pane">
        <SheetHeader>
          <SheetTitle>Run a strategy on paper</SheetTitle>
          <SheetDescription>Pick a strategy version and an instrument. The trader process starts it within ~10 s. Virtual money only.</SheetDescription>
        </SheetHeader>
        <form
          className="flex flex-col gap-4 p-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!chosenVersion || !instrument) return;
            await activate.mutateAsync({ version_id: chosenVersion, instrument_id: instrument.instrument_id });
            setOpen(false);
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rs-strategy">Strategy</Label>
            <select
              id="rs-strategy"
              value={strategyId ?? ""}
              onChange={(e) => {
                setStrategyId(e.target.value ? Number(e.target.value) : null);
                setVersionId(null);
              }}
              className="h-8 border border-border bg-raised px-2 text-xs"
            >
              <option value="">Select…</option>
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rs-version">Version</Label>
            <select
              id="rs-version"
              value={chosenVersion ?? ""}
              onChange={(e) => setVersionId(Number(e.target.value))}
              className="h-8 border border-border bg-raised px-2 text-xs"
              disabled={!strategyId}
            >
              {eligible.length === 0 && <option value="">No paper-eligible version</option>}
              {eligible.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_no} · {v.status}
                  {v.change_summary ? ` · ${v.change_summary}` : ""}
                </option>
              ))}
            </select>
            {chosenVersion && <StatusChip value={eligible.find((v) => v.id === chosenVersion)?.status ?? "draft"} />}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Instrument</Label>
            {instrument ? (
              <div className="flex items-center justify-between border border-border bg-raised px-2 py-1.5 text-xs">
                <span>{instrumentLabel(instrument)} · lot {instrument.lot_size}</span>
                <Button type="button" size="xs" variant="ghost" onClick={() => setInstrument(null)}>
                  change
                </Button>
              </div>
            ) : (
              <InstrumentSearch onPick={setInstrument} placeholder="Search NIFTY, BANKNIFTY, future…" />
            )}
          </div>
          {err && <p className="text-[11px] text-down">{err}</p>}
          <Button type="submit" disabled={!chosenVersion || !instrument || activate.isPending}>
            <Play /> Activate on paper
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
