"use client";

import { AlertTriangle, RefreshCw, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { OpenAsPanel } from "@/components/panels/OpenAsPanel";
import { EmptyState, PanelCard } from "@/components/design";
import { NewsList } from "@/components/news/NewsList";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { NewsSource } from "@/lib/api/generated";
import { useIngestNews, useNews, useNewsSources } from "@/lib/api/news";
import { useMe } from "@/lib/api/queries";
import { formatAge, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEL = "h-9 rounded-[var(--r-md)] border border-border bg-app px-2 text-[13px] text-text-1";

function feedState(s: NewsSource): { label: string; tone: string; problem: boolean } {
  if (s.last_fetch_error && !s.stale) return { label: "failing", tone: "text-down", problem: true };
  if (s.stale) return { label: "stale", tone: "text-warn", problem: true };
  if (!s.last_fetch_at && s.items === 0) return { label: "not fetched yet", tone: "text-text-3", problem: false };
  return { label: "ok", tone: "text-up", problem: false };
}

function SourcesPanel({ isOwner }: { isOwner: boolean }) {
  const { data, isPending, isError } = useNewsSources();
  const ingest = useIngestNews();
  return (
    <PanelCard
      title="Feeds"
      subtitle="RSS headlines only, every 30 min 07:00–22:30 IST"
      bodyClassName="p-0"
      actions={
        isOwner && (
          <Button size="xs" variant="ghost" onClick={() => ingest.mutate()} disabled={ingest.isPending} title="Queue one fetch of every feed in the worker">
            <RefreshCw className={cn("size-3", ingest.isPending && "animate-spin")} /> fetch now
          </Button>
        )
      }
    >
      {ingest.isSuccess && <p className="border-b border-border px-3 py-1.5 text-[12px] text-text-2">Fetch queued in the worker; the list refreshes in a few seconds.</p>}
      {isPending ? (
        <Skeleton className="m-3 h-20" />
      ) : isError ? (
        <EmptyState title="News service unavailable" description="The API did not answer." className="m-3" />
      ) : (
        <ul className="divide-y divide-border/60 text-[12px]">
          {data.sources.map((s) => {
            const st = feedState(s);
            return (
              <li key={s.feed_url} className="flex flex-col gap-0.5 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium text-text-1" title={s.feed_url}>
                    {s.source}
                    {!s.configured && <span className="ml-1 text-text-3">(removed from NEWS_FEEDS)</span>}
                  </span>
                  <span className={cn("shrink-0 font-mono text-[11px] uppercase", st.tone)}>{st.label}</span>
                </div>
                <div className="flex flex-wrap gap-x-3 text-[11px] text-text-3">
                  <span>{s.items} stored</span>
                  {s.last_fetch_at && (
                    <span>
                      last fetch {formatAge(s.last_fetch_at)} ago · {s.last_fetch_items ?? 0} in feed, {s.last_fetch_new ?? 0} new
                    </span>
                  )}
                  {s.newest_published_at && <span>newest {formatDateTime(s.newest_published_at)}</span>}
                </div>
                {st.problem && (s.last_fetch_error || s.last_error) && (
                  <p className="flex items-start gap-1 text-[11px] text-warn">
                    <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                    {s.last_fetch_error ?? s.last_error}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {data && (
        <p className="border-t border-border px-3 py-1.5 text-[11px] text-text-3">
          {data.last_run_at ? `Last run ${formatDateTime(data.last_run_at)}` : "No ingest run recorded yet."} Feeds come from NEWS_FEEDS on the server.
        </p>
      )}
    </PanelCard>
  );
}

function FilterForm({
  q,
  symbol,
  source,
  sources,
  filtered,
  onApply,
}: {
  q: string;
  symbol: string;
  source: string;
  sources: string[];
  filtered: boolean;
  onApply: (patch: Record<string, string>) => void;
}) {
  // Inputs start from the URL; the parent re-keys this form when the URL filter changes.
  const [qInput, setQInput] = useState(q);
  const [symInput, setSymInput] = useState(symbol);
  const set = onApply;
  return (
    <form
      className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2"
      onSubmit={(e) => {
        e.preventDefault();
        set({ q: qInput.trim(), symbol: symInput.trim().toUpperCase() });
      }}
    >
      <select aria-label="Source" className={SEL} value={source} onChange={(e) => set({ source: e.target.value })}>
        <option value="">All sources</option>
        {sources.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      <Input aria-label="Symbol" placeholder="Symbol, e.g. RELIANCE" value={symInput} onChange={(e) => setSymInput(e.target.value)} className="w-44 font-mono uppercase" />
      <Input aria-label="Search headlines" placeholder="Search headlines" value={qInput} onChange={(e) => setQInput(e.target.value)} className="w-56" />
      <Button type="submit" size="sm" variant="outline">
        <Search className="size-3.5" /> Apply
      </Button>
      {filtered && (
        <Button type="button" size="sm" variant="ghost" onClick={() => set({ source: "", symbol: "", q: "" })}>
          <X className="size-3.5" /> Clear
        </Button>
      )}
    </form>
  );
}

function NewsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const source = params.get("source") ?? "";
  const symbol = params.get("symbol") ?? "";
  const q = params.get("q") ?? "";
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const sources = useNewsSources();
  const news = useNews({ source: source || undefined, symbol: symbol || undefined, q: q || undefined, limit: 200 });

  const set = (patch: Record<string, string>) => {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    router.replace(`${pathname}${p.toString() ? `?${p}` : ""}`);
  };

  const problems = sources.data?.sources.filter((s) => s.configured && feedState(s).problem) ?? [];
  const filtered = Boolean(source || symbol || q);

  return (
    <div className="grid grid-cols-12 gap-3">
      <PanelCard
        title="News"
        subtitle="Raw headlines from public RSS feeds. No AI analysis yet (Stage 4); tags are plain name matching."
        className="col-span-12 xl:col-span-8"
        bodyClassName="p-0"
        actions={<OpenAsPanel panel="news" params={{ symbol: symbol || undefined }} />}
      >
        <FilterForm
          key={`${q}|${symbol}`}
          q={q}
          symbol={symbol}
          source={source}
          sources={sources.data?.sources.map((x) => x.source) ?? []}
          filtered={filtered}
          onApply={set}
        />
        {problems.length > 0 && (
          <p className="flex items-center gap-1.5 border-b border-border bg-warn-soft px-3 py-1.5 text-[12px] text-warn">
            <AlertTriangle className="size-3.5 shrink-0" />
            {problems.map((p) => p.source).join(", ")} {problems.length === 1 ? "is" : "are"} not delivering fresh headlines; see Feeds.
          </p>
        )}
        {news.isPending ? (
          <div className="flex flex-col gap-2 p-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : news.isError ? (
          <EmptyState title="News service unavailable" description="The API did not answer; nothing is shown rather than old copies." className="m-3" />
        ) : news.data.items.length === 0 ? (
          <EmptyState
            title={filtered ? "No headlines match" : "No headlines stored yet"}
            description={
              filtered
                ? symbol
                  ? `No stored headline mentions ${symbol} by name. Matching is deterministic (symbol and company name), so some stories may use another spelling.`
                  : "Try a wider filter."
                : "The worker fetches the feeds every 30 minutes between 07:00 and 22:30 IST. Owners can fetch now."
            }
            className="m-3"
          />
        ) : (
          <>
            <NewsList items={news.data.items} onSymbol={(s) => set({ symbol: s })} />
            <p className="border-t border-border px-3 py-1.5 text-[11px] text-text-3">
              {news.data.count} headline{news.data.count === 1 ? "" : "s"}
              {symbol && ` mentioning ${symbol} (searched the newest ${news.data.scanned})`} · times in IST · links open the publisher
            </p>
          </>
        )}
      </PanelCard>
      <div className="col-span-12 xl:col-span-4">
        <SourcesPanel isOwner={isOwner} />
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <NewsPage />
    </Suspense>
  );
}
