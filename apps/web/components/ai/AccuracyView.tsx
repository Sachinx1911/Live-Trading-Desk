"use client";

import { RefreshCw, Target } from "lucide-react";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAiAccuracy, useRebuildAiViewScores } from "@/lib/api/ai-views";
import type { AiAccuracy, AiAccuracyGroup, AiObservation, AiViewStatus } from "@/lib/api/generated";
import { useMe } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

const pct = (v: number | null | undefined, digits = 0) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);
const num = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const istTime = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });

const STATUS_CLASS: Record<AiViewStatus, string> = {
  pending: "text-text-3 border-border",
  hit: "text-up border-up/40",
  miss: "text-down border-down/40",
  void: "text-text-3 border-dashed border-border",
};

function StatusTag({ s }: { s: AiViewStatus }) {
  return <span className={cn("hud-label rounded-[var(--r-sm)] border px-1.5 py-0.5", STATUS_CLASS[s])}>{s}</span>;
}

/** Hit-rate bar (0–100 %) with the graded count; empty when nothing is graded. */
function RateBar({ g }: { g: AiAccuracyGroup }) {
  const graded = g.hits + g.misses;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-28 overflow-hidden rounded-full bg-raised">
        {g.hit_rate != null && <div className="absolute inset-y-0 left-0 bg-accent" style={{ width: `${g.hit_rate * 100}%` }} />}
      </div>
      <span className="w-10 text-right tabular text-text-1">{pct(g.hit_rate)}</span>
      <span className="text-[11px] text-text-3 tabular">n={graded}</span>
    </div>
  );
}

function GroupTable({ title, rows, keyLabel }: { title: string; rows: AiAccuracyGroup[]; keyLabel: string }) {
  return (
    <PanelCard title={title}>
      {rows.length === 0 ? (
        <p className="text-[12px] text-text-3">No views.</p>
      ) : (
        <table className="w-full text-[12px]">
          <thead>
            <tr className="hud-label text-left text-text-3">
              <th className="py-1 font-normal">{keyLabel}</th>
              <th className="py-1 font-normal">Hit-rate</th>
              <th className="py-1 text-right font-normal">H / M</th>
              <th className="py-1 text-right font-normal">Pend.</th>
              <th className="py-1 text-right font-normal">Void</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.key} className="border-t border-border/60">
                <td className="py-1 text-text-1">{g.key}</td>
                <td className="py-1">
                  <RateBar g={g} />
                </td>
                <td className="py-1 text-right tabular">
                  <span className="text-up">{g.hits}</span> / <span className="text-down">{g.misses}</span>
                </td>
                <td className="py-1 text-right tabular text-text-3">{g.pending}</td>
                <td className="py-1 text-right tabular text-text-3">{g.voids}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </PanelCard>
  );
}

/**
 * Calibration: per confidence band, what JARVIS promised (mean stated confidence of graded views,
 * amber tick) against what happened (hit-rate, bar). A calibrated JARVIS has the bar end on the tick.
 */
function Calibration({ data }: { data: AiAccuracy }) {
  return (
    <PanelCard title="Calibration" subtitle="is high confidence really more accurate?">
      <div className="flex flex-col gap-2.5">
        {data.by_confidence.map((g) => {
          const graded = g.hits + g.misses;
          return (
            <div key={g.key} className="grid grid-cols-[4.5rem_1fr_7rem] items-center gap-2 text-[12px]">
              <span className="tabular text-text-2">{g.key}</span>
              <div className="relative h-3 rounded-[var(--r-sm)] bg-raised" title={`hit-rate ${pct(g.hit_rate)} · stated ${pct(g.mean_confidence)}`}>
                {g.hit_rate != null && <div className="absolute inset-y-0 left-0 rounded-[var(--r-sm)] bg-accent/80" style={{ width: `${g.hit_rate * 100}%` }} />}
                {g.mean_confidence != null && (
                  <div className="absolute -inset-y-0.5 w-0.5 bg-amber" style={{ left: `calc(${g.mean_confidence * 100}% - 1px)` }} />
                )}
              </div>
              <span className="text-right tabular text-text-3">
                {graded ? (
                  <>
                    <span className="text-text-1">{pct(g.hit_rate)}</span> vs {pct(g.mean_confidence)} · n={graded}
                  </>
                ) : (
                  "not graded"
                )}
              </span>
            </div>
          );
        })}
        <p className="text-[11px] text-text-3">
          <span className="text-accent">▮</span> hit-rate · <span className="text-amber">|</span> mean stated confidence. Bands are lower-inclusive; 1.0 falls in 0.85–1. Small n means little.
        </p>
      </div>
    </PanelCard>
  );
}

function RecentTable({ rows }: { rows: AiObservation[] }) {
  return (
    <PanelCard title="Recent views" subtitle={`${rows.length} newest`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[56rem] text-[12px]">
          <thead>
            <tr className="hud-label text-left text-text-3">
              <th className="py-1 font-normal">Stated (IST)</th>
              <th className="py-1 font-normal">View</th>
              <th className="py-1 text-right font-normal">Conf.</th>
              <th className="py-1 font-normal">Reference</th>
              <th className="py-1 font-normal">Invalidation</th>
              <th className="py-1 font-normal">Due</th>
              <th className="py-1 font-normal">Status</th>
              <th className="py-1 text-right font-normal">Close / return</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.id} className="border-t border-border/60 align-top" title={o.statement ?? undefined}>
                <td className="py-1 tabular text-text-2">
                  {istTime(o.ts)}
                  <div className="text-[11px] text-text-3">
                    {o.caller}
                    {o.mode ? ` · ${o.mode}` : ""}
                  </div>
                </td>
                <td className="py-1 text-text-1">
                  {o.symbol} <span className={o.direction === "up" ? "text-up" : o.direction === "down" ? "text-down" : "text-text-2"}>{o.direction}</span>
                  <div className="text-[11px] text-text-3">{o.horizon_days} trading day{o.horizon_days === 1 ? "" : "s"}</div>
                </td>
                <td className="py-1 text-right tabular">{o.confidence.toFixed(2)}</td>
                <td className="py-1 tabular">
                  {num(o.ref_price)}
                  <div className="text-[11px] text-text-3">
                    {o.ref_source} · {o.ref_freshness} · {istTime(o.ref_ts)}
                  </div>
                </td>
                <td className="py-1 text-text-2">
                  {o.invalidation_price != null ? <span className="tabular">{num(o.invalidation_price)}</span> : "—"}
                  {o.invalidation && <div className="max-w-56 text-[11px] text-text-3">{o.invalidation}</div>}
                </td>
                <td className="py-1 tabular text-text-2">{o.due_date}</td>
                <td className="py-1">
                  <StatusTag s={o.status} />
                  {o.void_reason && <div className="max-w-48 text-[11px] text-text-3">{o.void_reason}</div>}
                </td>
                <td className="py-1 text-right tabular">
                  {o.close_price != null ? (
                    <>
                      {num(o.close_price)}
                      <div className={cn("text-[11px]", (o.return_pct ?? 0) >= 0 ? "text-up" : "text-down")}>
                        {o.return_pct != null ? `${o.return_pct >= 0 ? "+" : ""}${o.return_pct.toFixed(2)}%` : ""} (±{o.threshold_pct}%)
                      </div>
                    </>
                  ) : (
                    <span className="text-text-3">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PanelCard>
  );
}

function Spend({ data }: { data: AiAccuracy }) {
  const s = data.spend;
  const maxTok = Math.max(1, ...s.by_day.map((d) => d.input_tokens + d.output_tokens));
  return (
    <PanelCard title="AI spend" subtitle={`last ${s.days} days · ai_calls (inside this app; jarvis's own model spend is not here)`}>
      {s.total_calls === 0 ? (
        <EmptyState title="No AI calls recorded" description="Calls made by AI features in this app (NL builder, News Analyst) are logged in ai_calls with tokens and cost." />
      ) : (
        <div className="flex flex-col gap-2 text-[12px]">
          <div className="flex flex-wrap gap-x-5 tabular text-text-2">
            <span>
              <span className="text-text-1">{s.total_calls}</span> calls
            </span>
            <span>
              <span className="text-text-1">{(s.total_input_tokens + s.total_output_tokens).toLocaleString("en-IN")}</span> tokens
            </span>
            <span>
              cost <span className="text-text-1">{s.total_cost_usd == null ? "—" : `$${s.total_cost_usd.toFixed(4)}`}</span>
              {s.calls_without_cost > 0 && <span className="text-text-3"> ({s.calls_without_cost} calls without a cost)</span>}
            </span>
            <span className="text-text-3">daily token budget {s.daily_token_budget.toLocaleString("en-IN")}</span>
          </div>
          <table className="w-full">
            <tbody>
              {s.by_day.map((d) => {
                const tok = d.input_tokens + d.output_tokens;
                return (
                  <tr key={d.day} className="border-t border-border/60">
                    <td className="w-24 py-1 tabular text-text-2">{d.day}</td>
                    <td className="py-1">
                      <div className="h-2 rounded-full bg-raised">
                        <div className="h-2 rounded-full bg-amber/70" style={{ width: `${(tok / maxTok) * 100}%` }} />
                      </div>
                    </td>
                    <td className="w-32 py-1 text-right tabular text-text-2">{tok.toLocaleString("en-IN")} tok</td>
                    <td className="w-16 py-1 text-right tabular text-text-3">{d.calls}×</td>
                    <td className="w-20 py-1 text-right tabular text-text-1">{d.cost_usd == null ? "—" : `$${d.cost_usd.toFixed(4)}`}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PanelCard>
  );
}

/**
 * /ai/accuracy (Mark 1 Stage 4.6): how often JARVIS's directional views came true. Views are
 * recorded with a reference price taken by this app; the worker grades them after their horizon
 * from stored daily closes. Hit-rate = hits / (hits + misses); pending and void are never counted.
 */
export function AccuracyView() {
  const { data, isPending, isError } = useAiAccuracy(30);
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const rebuild = useRebuildAiViewScores();

  if (isPending) return <Skeleton className="h-48" />;
  if (isError || !data) {
    return (
      <PanelCard title="JARVIS accuracy">
        <EmptyState title="Cannot reach the API" />
      </PanelCard>
    );
  }
  const o = data.overall;
  const graded = o.hits + o.misses;
  const mixed = data.thresholds_in_use.length > 1 || (data.thresholds_in_use.length === 1 && data.thresholds_in_use[0] !== data.threshold_pct);

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title="JARVIS accuracy"
        subtitle={`threshold ±${data.threshold_pct}% · closes from ${data.provider.toUpperCase()} daily candles · void after ${data.grace_days} trading days without a close`}
        actions={
          isOwner && (
            <Button size="xs" variant="ghost" disabled={rebuild.isPending} onClick={() => rebuild.mutate()} title="Delete every grade and grade all views again in the worker">
              <RefreshCw className="size-3" /> rebuild scores
            </Button>
          )
        }
      >
        {rebuild.isSuccess && <p className="mb-2 text-[12px] text-text-2">Rebuild queued in the worker.</p>}
        {o.total === 0 ? (
          <EmptyState
            icon={Target}
            title="No views recorded yet"
            description="When JARVIS states a direction it records the view through the record_view tool; this page shows how often those views came true."
          />
        ) : (
          <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
            <div>
              <div className="hud-label text-text-3">Hit-rate</div>
              <div className="text-[34px] leading-none tabular text-text-1">{pct(o.hit_rate, 1)}</div>
              <div className="mt-1 text-[12px] text-text-3">{graded ? `${o.hits} of ${graded} graded views` : "no view graded yet"}</div>
            </div>
            <div className="flex gap-6 text-[12px] tabular">
              <div>
                <div className="hud-label text-text-3">Recorded</div>
                <div className="text-[18px] text-text-1">{o.total}</div>
              </div>
              <div>
                <div className="hud-label text-text-3">Hit / miss</div>
                <div className="text-[18px]">
                  <span className="text-up">{o.hits}</span> / <span className="text-down">{o.misses}</span>
                </div>
              </div>
              <div>
                <div className="hud-label text-text-3">Pending</div>
                <div className="text-[18px] text-text-2">{o.pending}</div>
              </div>
              <div>
                <div className="hud-label text-text-3">Void</div>
                <div className="text-[18px] text-text-2">{o.voids}</div>
              </div>
              <div>
                <div className="hud-label text-text-3">Mean conf.</div>
                <div className="text-[18px] text-text-2">{pct(o.mean_confidence)}</div>
              </div>
            </div>
            <p className="basis-full text-[11px] text-text-3">
              up = hit if the due-date close is ≥ +{data.threshold_pct}% from the reference price, down = hit if ≤ −{data.threshold_pct}%, sideways = hit if the move stays inside ±
              {data.threshold_pct}%. Pending and void views never enter a hit-rate. Views are never used by any strategy, risk check or order.
              {mixed && ` Stored grades use thresholds ${data.thresholds_in_use.join(", ")}%; rebuild to grade all with ±${data.threshold_pct}%.`}
            </p>
          </div>
        )}
      </PanelCard>

      {o.total > 0 && (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            <Calibration data={data} />
            <GroupTable title="By instrument" keyLabel="Instrument" rows={data.by_instrument} />
            <GroupTable title="By horizon" keyLabel="Trading days" rows={data.by_horizon} />
            <GroupTable title="By mode" keyLabel="Mode" rows={data.by_mode} />
            <GroupTable title="By caller" keyLabel="Caller" rows={data.by_caller} />
            <GroupTable title="By direction" keyLabel="Direction" rows={data.by_direction} />
          </div>
          <RecentTable rows={data.recent} />
        </>
      )}
      <Spend data={data} />
    </div>
  );
}
