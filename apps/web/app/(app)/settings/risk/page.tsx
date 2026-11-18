"use client";

import { Lock, Save } from "lucide-react";
import { useState } from "react";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { AccountPicker } from "@/components/trading/AccountPicker";
import { usePaperAccount } from "@/components/trading/usePaperAccount";
import { ApiRequestError } from "@/lib/api/client";
import type { ProductType, RiskLimits, RiskLimitsResponse } from "@/lib/api/generated";
import { usePaperRiskLimits, useSavePaperRiskLimits } from "@/lib/api/trading";
import { formatDateTime } from "@/lib/format";

const NUMBERS: { key: keyof RiskLimits; label: string; unit: string; step?: number }[] = [
  { key: "max_risk_per_trade_pct", label: "Max risk per trade", unit: "% of equity", step: 0.1 },
  { key: "max_daily_loss_pct", label: "Max daily loss", unit: "% of capital", step: 0.1 },
  { key: "max_weekly_loss_pct", label: "Max weekly loss", unit: "% of capital", step: 0.1 },
  { key: "max_drawdown_pct", label: "Drawdown that halves size", unit: "% from peak", step: 0.5 },
  { key: "max_open_positions", label: "Max open positions", unit: "count", step: 1 },
  { key: "max_lots_per_order", label: "Max lots per order", unit: "lots", step: 1 },
  { key: "max_exposure_pct", label: "Max gross exposure", unit: "% of equity", step: 5 },
  { key: "max_correlated_exposure_pct", label: "Max exposure per underlying", unit: "% of equity", step: 5 },
];
const TIMES: { key: keyof RiskLimits; label: string }[] = [
  { key: "trade_start", label: "First entry (IST)" },
  { key: "no_new_entries_after", label: "No new entries after" },
  { key: "square_off", label: "Square off intraday at" },
];
const PRODUCTS: ProductType[] = ["intraday", "delivery", "carry"];

function hhmm(v: string): string {
  return v.length >= 5 ? v.slice(0, 5) : v;
}

function Form({ accountId }: { accountId: number }) {
  const { data, isPending } = usePaperRiskLimits(accountId);
  if (isPending || !data) return <Skeleton className="h-64" />;
  // Keyed on version so a fresh server copy re-seeds the form instead of an effect.
  return <LimitsForm key={`${accountId}-${data.version}`} accountId={accountId} data={data} />;
}

function LimitsForm({ accountId, data }: { accountId: number; data: RiskLimitsResponse }) {
  const save = useSavePaperRiskLimits(accountId);
  const [form, setForm] = useState<RiskLimits>(() => ({
    ...data.limits,
    trade_start: hhmm(data.limits.trade_start),
    no_new_entries_after: hhmm(data.limits.no_new_entries_after),
    square_off: hhmm(data.limits.square_off),
  }));
  const [saved, setSaved] = useState(false);
  const locked = data.edit_locked;
  const err = save.error instanceof ApiRequestError ? save.error.message : save.error ? "Cannot reach the API." : null;
  const set = <K extends keyof RiskLimits>(k: K, v: RiskLimits[K]) => setForm({ ...form, [k]: v });
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaved(false);
        await save.mutateAsync(form);
        setSaved(true);
      }}
    >
      {locked && (
        <div className="flex items-center gap-2 rounded-sm border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
          <Lock className="size-3.5" /> {data.edit_lock_reason ?? "Editing locked"}
        </div>
      )}
      <p className="text-[11px] text-text-3">
        {data.is_default ? "Using platform defaults (not saved yet)." : `Version ${data.version}, effective ${data.effective_from ? formatDateTime(data.effective_from) : "—"}.`} Limits change outside market hours only, by design.
      </p>
      <fieldset disabled={locked} className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {NUMBERS.map((f) => (
          <div key={f.key} className="flex flex-col gap-1.5">
            <Label htmlFor={`rl-${f.key}`}>{f.label}</Label>
            <div className="flex items-center gap-2">
              <Input id={`rl-${f.key}`} type="number" step={f.step ?? 1} min={0} value={String(form[f.key])} onChange={(e) => set(f.key, Number(e.target.value) as never)} className="h-8 text-xs tabular" />
              <span className="shrink-0 text-[11px] text-text-3">{f.unit}</span>
            </div>
          </div>
        ))}
        {TIMES.map((f) => (
          <div key={f.key} className="flex flex-col gap-1.5">
            <Label htmlFor={`rl-${f.key}`}>{f.label}</Label>
            <Input id={`rl-${f.key}`} type="time" value={String(form[f.key])} onChange={(e) => set(f.key, e.target.value as never)} className="h-8 text-xs tabular" />
          </div>
        ))}
        <div className="flex flex-col gap-2 text-xs">
          <Label>Products allowed</Label>
          {PRODUCTS.map((p) => (
            <label key={p} className="flex items-center gap-2 text-text-2">
              <input
                type="checkbox"
                checked={form.allowed_products.includes(p)}
                onChange={(e) => set("allowed_products", e.target.checked ? [...form.allowed_products, p] : form.allowed_products.filter((x) => x !== p))}
              />
              {p}
            </label>
          ))}
        </div>
        <div className="flex flex-col gap-2 text-xs">
          <Label>Toggles</Label>
          <label className="flex items-center gap-2 text-text-2"><input type="checkbox" checked={form.allow_short} onChange={(e) => set("allow_short", e.target.checked)} /> allow short entries</label>
          <label className="flex items-center gap-2 text-text-2"><input type="checkbox" checked={form.event_block} onChange={(e) => set("event_block", e.target.checked)} /> block entries on high-impact event days</label>
          <label className="flex items-center gap-2 text-text-2"><input type="checkbox" checked={form.freeze_quantity_check} onChange={(e) => set("freeze_quantity_check", e.target.checked)} /> enforce exchange freeze quantity</label>
        </div>
      </fieldset>
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" disabled={locked || save.isPending}>
          <Save /> Save as new version
        </Button>
        {saved && <span className="text-[11px] text-up">Saved.</span>}
        {err && <span className="text-[11px] text-down">{err}</span>}
      </div>
    </form>
  );
}

export default function RiskSettingsPage() {
  const { accountId, accounts } = usePaperAccount();
  return (
    <PanelCard title="Risk limits" subtitle="Hard limits the risk engine enforces on every signal. Versioned; the trader reloads them within 10 s." actions={<AccountPicker />}>
      {accounts && accounts.length === 0 ? (
        <EmptyState title="No paper account yet" description="Create one on the Paper Trading page, then set its limits here." />
      ) : accountId != null ? (
        <Form key={accountId} accountId={accountId} />
      ) : (
        <Skeleton className="h-64" />
      )}
    </PanelCard>
  );
}
