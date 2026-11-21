"use client";

import { ExternalLink } from "lucide-react";
import type { NewsItem } from "@/lib/api/generated";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Headline rows: time (IST), source, title linking out to the publisher, feed summary and the
 * deterministic symbol tags. Nothing here is AI output; we never host article bodies.
 */
export function NewsList({
  items,
  compact = false,
  onSymbol,
  className,
}: {
  items: NewsItem[];
  compact?: boolean;
  onSymbol?: (symbol: string) => void;
  className?: string;
}) {
  return (
    <ul className={cn("divide-y divide-border/60", className)}>
      {items.map((n) => (
        <li key={n.id} className={cn("flex flex-col gap-1 px-3", compact ? "py-2" : "py-2.5")}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-text-3">
            <span className="tabular" title={n.published_at ? "Published" : "Feed gave no time; shown when we fetched it"}>
              {formatDateTime(n.published_at ?? n.fetched_at)}
              {!n.published_at && " (fetched)"}
            </span>
            <span className="text-text-2">{n.source}</span>
            {n.symbols.map((s) =>
              onSymbol ? (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSymbol(s)}
                  className="rounded-[var(--r-sm)] border border-border px-1 font-mono text-[10px] text-cyan-accent hover:border-border-strong"
                  title={`Show only ${s}`}
                >
                  {s}
                </button>
              ) : (
                <span key={s} className="rounded-[var(--r-sm)] border border-border px-1 font-mono text-[10px] text-cyan-accent">
                  {s}
                </span>
              ),
            )}
          </div>
          <a
            href={n.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className={cn("group inline-flex items-start gap-1 text-text-1 hover:text-accent-text", compact ? "text-[12px]" : "text-[13px] font-medium")}
          >
            <span>{n.title}</span>
            <ExternalLink className="mt-0.5 size-3 shrink-0 text-text-3 group-hover:text-accent-text" aria-label="opens the publisher's site" />
          </a>
          {!compact && n.summary && <p className="line-clamp-2 text-[12px] text-text-3">{n.summary}</p>}
        </li>
      ))}
    </ul>
  );
}
