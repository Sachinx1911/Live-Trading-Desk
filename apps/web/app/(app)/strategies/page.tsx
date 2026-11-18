"use client";

import { Archive, FlaskConical, Plus, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EmptyState, PanelCard } from "@/components/design";
import { StatusChip } from "@/components/trading/StatusChip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/lib/api/client";
import type { StrategyCategory, StrategyOrigin } from "@/lib/api/generated";
import { useArchiveStrategy, useCreateStrategy, useStrategies } from "@/lib/api/trading";
import { formatDateTime } from "@/lib/format";

const CATEGORIES: StrategyCategory[] = ["trend", "mean_reversion", "breakout", "options", "swing", "other"];
const ORIGINS: StrategyOrigin[] = ["user_visual", "user_nl", "import"];

function CreateForm({ onDone }: { onDone: (id: number) => void }) {
  const create = useCreateStrategy();
  const [name, setName] = useState("");
  const [category, setCategory] = useState<StrategyCategory>("trend");
  const [origin, setOrigin] = useState<StrategyOrigin>("user_visual");
  const [desc, setDesc] = useState("");
  const [tags, setTags] = useState("");
  const err = create.error instanceof ApiRequestError ? create.error.message : null;
  return (
    <form
      className="grid gap-3 md:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        const s = await create.mutateAsync({ name: name.trim(), category, origin, description: desc || null, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) });
        onDone(s.id);
      }}
    >
      <div className="flex flex-col gap-1.5 md:col-span-2">
        <Label htmlFor="st-name">Name</Label>
        <Input id="st-name" required value={name} onChange={(e) => setName(e.target.value)} className="h-8 text-xs" />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="st-cat">Category</Label>
        <select id="st-cat" value={category} onChange={(e) => setCategory(e.target.value as StrategyCategory)} className="h-8 rounded-sm border border-border-subtle bg-panel-raised px-2 text-xs">
          {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="st-origin">Origin</Label>
        <select id="st-origin" value={origin} onChange={(e) => setOrigin(e.target.value as StrategyOrigin)} className="h-8 rounded-sm border border-border-subtle bg-panel-raised px-2 text-xs">
          {ORIGINS.map((o) => <option key={o} value={o}>{o.replace("_", " ")}</option>)}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="st-desc">Description</Label>
        <Input id="st-desc" value={desc} onChange={(e) => setDesc(e.target.value)} className="h-8 text-xs" />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="st-tags">Tags (comma separated)</Label>
        <Input id="st-tags" value={tags} onChange={(e) => setTags(e.target.value)} className="h-8 text-xs" />
      </div>
      <div className="flex items-center gap-2 md:col-span-2">
        <Button type="submit" size="sm" disabled={create.isPending}><Plus /> Create strategy</Button>
        <span className="text-[11px] text-text-muted">Then add a version by pasting a DSL document (examples: ema_rsi_nifty, banknifty_vwap_reversion, nifty50_daily_breakout).</span>
        {err && <span className="text-[11px] text-pnl-negative">{err}</span>}
      </div>
    </form>
  );
}

export default function StrategiesPage() {
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const { data, isPending, isError } = useStrategies(archived);
  const archive = useArchiveStrategy();
  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title="Strategy library"
        subtitle="Versions are immutable once they leave draft; every change is a new version."
        actions={
          <>
            <label className="flex items-center gap-1 text-[11px] text-text-secondary"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> show archived</label>
            <Link href="/strategies/new/natural-language" className="text-[11px] text-ai"><Wand2 className="mr-1 inline size-3" />NL builder (Phase 5)</Link>
            <Button size="sm" onClick={() => setCreating((v) => !v)}><Plus /> New strategy</Button>
          </>
        }
      >
        {creating && <div className="mb-3 rounded-sm border border-border-subtle p-3"><CreateForm onDone={() => setCreating(false)} /></div>}
        {isPending ? (
          <Skeleton className="h-32" />
        ) : isError ? (
          <EmptyState title="Cannot load strategies" />
        ) : !data || data.length === 0 ? (
          <EmptyState icon={FlaskConical} title="No strategies yet" description="Create one, then paste a DSL version to run it on paper." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.map((s) => (
              <div key={s.id} className="flex flex-col gap-2 rounded-md border border-border-subtle bg-panel-raised p-3">
                <div className="flex items-start justify-between gap-2">
                  <Link href={`/strategies/${s.id}`} className="text-sm font-semibold text-text-primary hover:text-accent-cyan">{s.name}</Link>
                  {s.latest_version ? <StatusChip value={s.latest_version.status} /> : <StatusChip value="no version" tone="muted" />}
                </div>
                <p className="text-[11px] text-text-secondary">{s.category.replace("_", " ")} · {s.origin.replace("_", " ")} · created {formatDateTime(s.created_at)}</p>
                {s.description && <p className="text-xs text-text-secondary">{s.description}</p>}
                {s.tags.length > 0 && <p className="text-[11px] text-text-muted">{s.tags.map((t) => `#${t}`).join(" ")}</p>}
                <div className="mt-auto flex items-center justify-between pt-1 text-[11px]">
                  <span className="text-text-muted">{s.latest_version ? `v${s.latest_version.version_no} · ${s.latest_version.dsl_schema_version}` : "—"}</span>
                  {!s.is_archived && (
                    <Button size="xs" variant="ghost" onClick={() => archive.mutate(s.id)} aria-label="Archive"><Archive /> archive</Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </PanelCard>
    </div>
  );
}
