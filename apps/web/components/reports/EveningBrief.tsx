"use client";

/**
 * Evening brief (Mark 1 Stage 3.3/3.7): the stored end-of-day record, rendered from its
 * structured content. Every section shows "not stored" when the source had no data; nothing
 * is filled in on the client.
 */
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { OpenAsPanel } from "@/components/panels/OpenAsPanel";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api/client";
import type { DailyReportContent } from "@/lib/api/generated";
import { useDailyReport, useDailyReports, useGenerateDailyReport } from "@/lib/api/reports";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function Signed({ v, suffix = "" }: { v: string | null; suffix?: string }) {
  if (v === null) return <span className="text-text-3">n/a</span>;
  const n = Number(v);
  return <span className={cn("tabular", n > 0 ? "text-up" : n < 0 ? "text-down" : "")}>{n > 0 ? "+" : ""}{v}{suffix}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border border-border p-2">
      <p className="text-[10px] uppercase tracking-wide text-text-3">{title}</p>
      {children}
    </div>
  );
}

/** Structured brief content; shared with the brief panel (/panel/brief). */
export function EveningBriefBody({ c }: { c: DailyReportContent }) {
  const missing = c.coverage.filter((x) => !x.complete);
  return (
    <div className="grid gap-2 text-xs md:grid-cols-2 xl:grid-cols-3">
      <Section title="Indices">
        {c.indices.length === 0 && <span className="text-text-3">No index candles stored.</span>}
        {c.indices.map((m) => (
          <div key={m.symbol} className="flex justify-between">
            <span>{m.symbol}</span>
            {m.close === null ? <span className="text-text-3">no close stored</span> : (
              <span className="tabular">{m.close} <Signed v={m.change} /> (<Signed v={m.change_pct} suffix="%" />)</span>
            )}
          </div>
        ))}
      </Section>
      <Section title="PCR at close">
        {c.pcr.length === 0 && <span className="text-text-3">No chain snapshots stored.</span>}
        {c.pcr.map((p) => (
          <div key={p.symbol} className="flex justify-between">
            <span>{p.symbol}</span>
            {p.pcr === null ? <span className="text-text-3">no snapshot</span> : <span className="tabular">{Number(p.pcr).toFixed(2)} <span className="text-text-3">exp {p.expiry}</span></span>}
          </div>
        ))}
      </Section>
      <Section title="Breadth · NIFTY 50">
        {c.breadth === null ? <span className="text-text-3">Not computed for this day.</span> : (
          <>
            <div className="flex justify-between"><span>Advances / declines</span><span className="tabular"><span className="text-up">{c.breadth.advances}</span> / <span className="text-down">{c.breadth.declines}</span> · {c.breadth.unchanged} flat</span></div>
            <div className="flex justify-between"><span>Above EMA 200</span><span className="tabular">{c.breadth.above_ema200_pct ?? "n/a"}{c.breadth.above_ema200_pct ? "%" : ""}</span></div>
            <div className="flex justify-between"><span>52w highs / lows</span><span className="tabular">{c.breadth.new_52w_high} / {c.breadth.new_52w_low}</span></div>
          </>
        )}
      </Section>
      <Section title="Paper trading">
        {c.paper.length === 0 && <span className="text-text-3">No active paper account.</span>}
        {c.paper.map((a) => (
          <div key={a.account_id} className="flex flex-col">
            <div className="flex justify-between"><span>{a.name}</span><Signed v={a.net_pnl} /></div>
            <span className="text-text-3">{a.trades} trades · {a.wins} wins · {a.open_positions} open · cash {a.cash}</span>
          </div>
        ))}
        <span className="text-text-3">
          Alerts: {Object.entries(c.alerts.by_severity).map(([k, v]) => `${k} ${v}`).join(", ") || "none"} · owner-rule blocks {c.alerts.rule_blocks}
        </span>
      </Section>
      <Section title="Data completeness · 1-minute bars">
        {c.coverage.length === 0 && <span className="text-text-3">No tracked symbols.</span>}
        {c.coverage.length > 0 && missing.length === 0 && <span className="text-up">All {c.coverage.length} tracked symbols complete.</span>}
        {missing.map((x) => (
          <div key={x.symbol} className="flex justify-between"><span>{x.symbol}</span><span className="tabular text-warn">{x.bars}/{x.expected}</span></div>
        ))}
      </Section>
      <Section title="Next session">
        <span className="tabular">{c.next_trading_day ?? "—"}</span>
        {c.expiries_next_7d.map((e) => <span key={`${e.symbol}${e.expiry}`} className="text-text-2">Expiry {e.symbol} {e.expiry}</span>)}
      </Section>
      {c.headlines.length > 0 && (
        <div className="md:col-span-2 xl:col-span-3">
          <Section title="Headlines">
            {c.headlines.map((h) => (
              <a key={h.url} href={h.url} target="_blank" rel="noreferrer" className="truncate hover:text-accent">{h.title} <span className="text-text-3">· {h.source}</span></a>
            ))}
          </Section>
        </div>
      )}
    </div>
  );
}

export function EveningBrief() {
  const { data: list } = useDailyReports();
  const [day, setDay] = useState<string | null>(null);
  const { data: report, isPending, error } = useDailyReport(day);
  const gen = useGenerateDailyReport();
  const notFound = error instanceof ApiRequestError && error.status === 404;
  return (
    <PanelCard
      title="Evening brief"
      subtitle={report ? `${report.content.date} · ${report.content.provider} · generated ${formatDateTime(report.created_at)} · Telegram ${String(report.delivered.telegram ?? "skipped")}` : "End-of-day record from stored data (no AI)"}
      className="col-span-12"
      actions={
        <div className="flex items-center gap-2">
          <select aria-label="Report day" value={day ?? ""} onChange={(e) => setDay(e.target.value || null)} className="h-7 border border-border bg-raised px-2 text-xs">
            <option value="">Latest</option>
            {(list ?? []).map((r) => <option key={r.report_date} value={r.report_date}>{r.report_date}</option>)}
          </select>
          <Button size="xs" variant="outline" disabled={gen.isPending} onClick={() => gen.mutate({ day })}>
            <RefreshCw /> {gen.isSuccess ? "Queued" : "Regenerate"}
          </Button>
          <OpenAsPanel panel="brief" params={{ date: day }} />
        </div>
      }
    >
      {isPending ? <p className="text-xs text-text-3">Loading…</p> : notFound || !report ? (
        <EmptyState title="No brief yet" description="It is generated after each session at 19:00 IST, or with Regenerate." />
      ) : (
        <>
          {!report.content.is_trading_day && <p className="mb-2 text-xs text-text-3">Market closed on this day.</p>}
          <EveningBriefBody c={report.content} />
        </>
      )}
    </PanelCard>
  );
}
