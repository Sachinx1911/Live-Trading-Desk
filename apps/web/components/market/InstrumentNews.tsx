"use client";

import Link from "next/link";
import { EmptyState, PanelCard } from "@/components/design";
import { NewsList } from "@/components/news/NewsList";
import { Skeleton } from "@/components/ui/skeleton";
import type { Segment } from "@/lib/api/generated";
import { useNews } from "@/lib/api/news";

/** Latest raw headlines that name the selected stock or index (deterministic matching, no AI). */
export function InstrumentNews({ symbol, segment, className }: { symbol: string | null; segment: Segment | null; className?: string }) {
  const supported = segment === "equity" || segment === "index";
  const q = useNews({ symbol: symbol ?? undefined, limit: 8 }, Boolean(symbol) && supported);
  const more = symbol ? (
    <Link href={`/news?symbol=${encodeURIComponent(symbol)}`} className="text-[11px] text-accent-text hover:underline">
      all news
    </Link>
  ) : null;

  return (
    <PanelCard title="News" subtitle={symbol ? `Headlines naming ${symbol}` : undefined} actions={supported ? more : null} className={className} bodyClassName="p-0">
      {!symbol ? (
        <EmptyState title="No instrument selected" className="m-3" />
      ) : !supported ? (
        <EmptyState title="News is matched to stocks and indices" description="Select the underlying to see its headlines." className="m-3" />
      ) : q.isPending ? (
        <Skeleton className="m-3 h-16" />
      ) : q.isError ? (
        <EmptyState title="News service unavailable" className="m-3" />
      ) : q.data.items.length === 0 ? (
        <EmptyState title={`No stored headline names ${symbol}`} description="Feeds are fetched every 30 min, 07:00–22:30 IST." className="m-3" />
      ) : (
        <NewsList items={q.data.items} compact />
      )}
    </PanelCard>
  );
}
