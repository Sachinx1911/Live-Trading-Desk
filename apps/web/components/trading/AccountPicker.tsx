"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import { ModeTag } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiRequestError } from "@/lib/api/client";
import { useCreatePaperAccount } from "@/lib/api/trading";
import { usePaperAccount } from "./usePaperAccount";

export function CreateAccountForm({ onDone, compact = false }: { onDone?: (id: number) => void; compact?: boolean }) {
  const create = useCreatePaperAccount();
  const [name, setName] = useState("Paper account");
  const [capital, setCapital] = useState("100000");
  const err = create.error instanceof ApiRequestError ? create.error.message : create.error ? "Cannot reach the API." : null;
  return (
    <form
      className={compact ? "flex items-end gap-2" : "flex flex-col gap-3"}
      onSubmit={async (e) => {
        e.preventDefault();
        const cap = Number(capital);
        const a = await create.mutateAsync({ name: name.trim() || "Paper account", initial_capital: cap > 0 ? cap : null });
        onDone?.(a.id);
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="pa-name">Name</Label>
        <Input id="pa-name" value={name} onChange={(e) => setName(e.target.value)} className="h-8 text-xs" />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="pa-cap">Virtual capital (₹)</Label>
        <Input id="pa-cap" type="number" min={1000} step={1000} value={capital} onChange={(e) => setCapital(e.target.value)} className="h-8 w-36 text-xs tabular" />
      </div>
      <Button type="submit" size="sm" disabled={create.isPending}>
        <Plus /> Create
      </Button>
      {err && <p className="text-[11px] text-down">{err}</p>}
    </form>
  );
}

export function AccountPicker() {
  const { accounts, accountId, select } = usePaperAccount();
  if (!accounts || accounts.length === 0) return null;
  return (
    <div className="flex items-center gap-2">
      <ModeTag mode="paper" />
      <select
        aria-label="Paper account"
        value={accountId ?? ""}
        onChange={(e) => select(Number(e.target.value))}
        className="h-7 border border-border bg-raised px-2 text-xs text-text-1"
      >
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} · #{a.id}
          </option>
        ))}
      </select>
    </div>
  );
}
