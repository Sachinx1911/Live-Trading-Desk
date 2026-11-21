"use client";

import { Suspense } from "react";
import { NewsList } from "@/components/news/NewsList";
import { PanelFrame, PanelMessage, PanelParamErrors } from "@/components/panels/PanelFrame";
import { usePanelParams } from "@/components/panels/usePanel";
import { useNews } from "@/lib/api/news";
import { formatDateTime } from "@/lib/format";
import { fullPageUrl } from "@/lib/panels";

/** Stored RSS headlines (no AI); links open the publisher. Fetching stays on /news. */
function NewsPanel() {
  const { values, errors: paramErrors } = usePanelParams("news");
  const symbol = values.symbol;
  const limit = values.limit != null ? Number(values.limit) : 50;
  const errors = [...paramErrors];
  if (values.limit != null && (limit < 1 || limit > 200)) errors.push({ param: "limit", message: `${limit} is outside 1-200` });
  const q = useNews({ symbol, limit }, errors.length === 0);
  const newest = q.data?.items[0];

  const frame = (children: React.ReactNode) => (
    <PanelFrame
      panel="news"
      subtitle={symbol ? `headlines naming ${symbol}` : "all feeds"}
      state={q.data ? "historical" : q.isError ? "disconnected" : undefined}
      stateDetail={newest ? `newest ${formatDateTime(newest.published_at ?? newest.fetched_at)}` : q.data ? "none stored" : undefined}
      source="rss"
      fullHref={symbol ? `/news?symbol=${encodeURIComponent(symbol)}` : fullPageUrl("news")}
    >
      {children}
    </PanelFrame>
  );

  if (errors.length) return frame(<PanelParamErrors panel="news" errors={errors} />);
  if (q.isError) return frame(<PanelMessage tone="error" title="News service unavailable" />);
  if (q.isPending) return frame(<PanelMessage title="Loading headlines…" />);
  if (q.data.items.length === 0)
    return frame(<PanelMessage title={symbol ? `No stored headline names ${symbol}` : "No headlines stored yet"} description="Feeds are fetched every 30 min, 07:00–22:30 IST." />);
  return frame(<NewsList items={q.data.items} />);
}

export default function NewsPanelPage() {
  return (
    <Suspense>
      <NewsPanel />
    </Suspense>
  );
}
