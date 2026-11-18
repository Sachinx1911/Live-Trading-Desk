"use client";

import { Database, History, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { DataStateBadge, DemoBanner, EmptyState, PanelCard } from "@/components/design";
import { ReplayChart, useContextCandles } from "@/components/replay/ReplayChart";
import { ReplayPanels } from "@/components/replay/ReplayPanels";
import { ReplaySetupForm } from "@/components/replay/ReplaySetupForm";
import { TransportBar } from "@/components/replay/TransportBar";
import { useReplayStream } from "@/components/replay/useReplayStream";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/lib/api/client";
import type { Instrument, ReplaySessionIn, ReplaySessionOut, StrategyVersion } from "@/lib/api/generated";
import { useInstrument } from "@/lib/api/queries";
import {
  deleteReplaySessionOnUnload,
  useCreateReplaySession,
  useDeleteReplaySession,
  useReplaySessions,
} from "@/lib/api/replay";
import { useStrategyVersion } from "@/lib/api/trading";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Same shape as ModeTag, but a third mode: nothing on this page is paper or live. */
function ReplayTag({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full bg-warn/15 px-2 text-[11px] font-semibold uppercase tracking-wide text-warn",
        className,
      )}
      aria-label="Historical replay, not live"
    >
      <History className="size-3" /> Replay
    </span>
  );
}

function ExistingSessions({ onResume, current }: { onResume: (s: ReplaySessionOut) => void; current: string | null }) {
  const { data, isPending } = useReplaySessions();
  const del = useDeleteReplaySession();
  const others = (data ?? []).filter((s) => s.session_id !== current);
  if (isPending) return <Skeleton className="h-16" />;
  if (others.length === 0) return null;
  return (
    <PanelCard title="Open sessions" subtitle="Still alive on the API; idle sessions are swept automatically" bodyClassName="p-0">
      <table className="w-full text-xs">
        <tbody>
          {others.map((s) => (
            <tr key={s.session_id} className="border-b border-border/60">
              <td className="px-3 py-1.5 tabular text-text-2">{s.date}</td>
              <td className="px-3 py-1.5 text-text-2">#{s.instrument_id} · {s.timeframe}{s.strategy_version_id ? ` · v#${s.strategy_version_id}` : ""}</td>
              <td className="px-3 py-1.5 tabular text-text-3">{s.state.cursor}/{s.bars} · {s.state.status}</td>
              <td className="px-3 py-1.5 text-right">
                <Button size="xs" variant="ghost" onClick={() => onResume(s)}>Resume</Button>
                <Button size="icon-xs" variant="ghost" aria-label="Delete session" disabled={del.isPending} onClick={() => del.mutate(s.session_id)}>
                  <Trash2 />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelCard>
  );
}

function CreateError({ error, body, symbol }: { error: unknown; body: ReplaySessionIn | null; symbol?: string }) {
  if (!(error instanceof ApiRequestError) || !body) return null;
  const what = symbol ? `${symbol} (#${body.instrument_id})` : `instrument #${body.instrument_id}`;
  // The API answers 404 with FastAPI's {detail} body, which the client does not surface; the
  // only other 404s on this endpoint are "strategy version / instrument not found".
  if (error.status === 404 && !/strategy|instrument/i.test(error.message)) {
    return (
      <EmptyState
        icon={Database}
        title={`No 1-minute candles for ${what} on ${body.date}`}
        description="Nothing is stored for that instrument on that day, so there is nothing to replay. Check data coverage and run a backfill from the Market page."
        className="min-h-48"
      />
    );
  }
  if (error.status === 400) {
    return <EmptyState title={`${body.date} is not a trading day`} description="Pick an NSE trading day. Weekends and exchange holidays have no session." className="min-h-48" />;
  }
  if (error.status === 409) {
    return <EmptyState title="Session limit reached" description={`${error.message}. End or delete an open session below and try again.`} className="min-h-48" />;
  }
  return null;
}

/** Unmount deletes waiting out a possible immediate remount (React StrictMode). */
const pendingDeletes = new Map<string, ReturnType<typeof setTimeout>>();

type Active = {
  session: ReplaySessionOut;
  instrument: Instrument | null;
  version: StrategyVersion | null;
};

function ActiveReplay({ active, onEnd }: { active: Active; onEnd: () => void }) {
  const { session } = active;
  const tf = session.timeframe;
  const { data: fetchedInstrument } = useInstrument(active.instrument ? null : session.instrument_id);
  const instrument = active.instrument ?? fetchedInstrument ?? null;
  const { data: fetchedVersion } = useStrategyVersion(active.version || !session.strategy_version_id ? null : session.strategy_version_id);
  const version = active.version ?? fetchedVersion ?? null;
  const stream = useReplayStream(session.session_id, tf);
  const ctx = useContextCandles(session.instrument_id, session.date, tf, true);
  const del = useDeleteReplaySession();
  const symbol = instrument?.symbol ?? `#${session.instrument_id}`;
  const hasStrategy = session.strategy_version_id != null;
  const state = stream.state;
  // The session streams whatever 1-minute rows are stored for the day, from any provider.
  // If demo rows are among them the chart carries the demo banner, never a clean label.
  const demoBars = stream.bars.filter((b) => b.is_demo).length;

  // End = delete the session on the API. Also on tab close and on navigating away. The
  // unmount delete is deferred and cancelled on remount so React's dev double-mount does
  // not kill a session that is still on screen.
  const endedRef = useRef(false);
  useEffect(() => {
    const id = session.session_id;
    const pending = pendingDeletes.get(id);
    if (pending) {
      clearTimeout(pending);
      pendingDeletes.delete(id);
    }
    const onHide = () => {
      if (!endedRef.current) deleteReplaySessionOnUnload(id);
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      if (endedRef.current) return;
      pendingDeletes.set(
        id,
        setTimeout(() => {
          pendingDeletes.delete(id);
          deleteReplaySessionOnUnload(id);
        }, 1000),
      );
    };
  }, [session.session_id]);

  const end = () => {
    endedRef.current = true;
    del.mutate(session.session_id);
    onEnd();
  };

  return (
    <div className="grid grid-cols-12 gap-3">
      <PanelCard
        title={
          <span className="flex items-center gap-2">
            {symbol} · {tf}
            <ReplayTag />
          </span>
        }
        subtitle={`${session.date} · ${session.bars} one-minute bars${hasStrategy && version ? ` · strategy v${version.version_no}` : ""}`}
        className="col-span-12 xl:col-span-8"
        bodyClassName="p-0"
        banner={demoBars > 0 ? <DemoBanner /> : undefined}
        actions={
          <>
            {(demoBars > 0 || ctx.data?.is_demo) && <DataStateBadge state="demo" detail={demoBars > 0 ? `${demoBars} bars` : "context"} />}
            <DataStateBadge state="historical" detail={state?.cursor_ts ? formatTime(state.cursor_ts) : undefined} />
          </>
        }
      >
        {demoBars > 0 && (
          <p className="border-b border-border px-3 py-1 text-[11px] text-ai">
            {demoBars} of the streamed bars are demo rows from the fake provider, mixed into the stored day by the API. Their prices are synthetic.
          </p>
        )}
        <div className="relative">
          <div className="pointer-events-none absolute top-2 left-3 z-10 flex items-baseline gap-2 opacity-70">
            <span className="text-[16px] text-text-1">{symbol}</span>
            <span className="text-[13px] text-text-2">{tf}</span>
            {stream.bars.length > 0 && (() => {
              const b = stream.bars[stream.bars.length - 1];
              const up = Number(b.close) >= Number(b.open);
              return (
                <span className="tabular text-[13px] text-text-2">
                  O {Number(b.open).toFixed(2)} H {Number(b.high).toFixed(2)} L {Number(b.low).toFixed(2)} C{" "}
                  <span className={up ? "text-up" : "text-down"}>{Number(b.close).toFixed(2)}</span>
                </span>
              );
            })()}
            {stream.lastQuote && (
              <span className="tabular text-[12px] text-text-3">last 1m close {Number(stream.lastQuote.ltp).toFixed(2)}</span>
            )}
          </div>
          {ctx.data && ctx.data.candles.length > 0 && (
            <span className="pointer-events-none absolute top-2 right-16 z-10 text-[11px] text-text-3">
              dimmed: {ctx.data.candles.length} stored {tf} bars before {session.date}
            </span>
          )}
          <ReplayChart bars={stream.bars} contextBars={ctx.data?.candles ?? []} events={stream.events} timeframe={tf} />
          {stream.bars.length === 0 && (
            <div className="pointer-events-none absolute inset-x-0 bottom-24 z-10 text-center text-[12px] text-text-3">
              {stream.wsState === "connected" ? "Press play or step to stream the first bar." : stream.wsState === "gone" ? "This session no longer exists on the API." : "Connecting to the replay stream…"}
            </div>
          )}
        </div>
        {stream.lastError && (
          <div className="flex items-center justify-between border-t border-border px-3 py-1 text-[11px] text-down">
            {stream.lastError}
            <Button size="xs" variant="ghost" onClick={stream.clearError}>dismiss</Button>
          </div>
        )}
        <TransportBar state={state} wsState={stream.wsState} send={stream.send} onEnd={end} ending={del.isPending} />
      </PanelCard>
      <PanelCard
        title="Session"
        subtitle={hasStrategy ? "Signals, risk decisions, orders, fills, trades" : "Bars only; attach a strategy to see signals"}
        className="col-span-12 xl:col-span-4"
        bodyClassName="p-0"
        actions={<ReplayTag />}
      >
        <ReplayPanels
          events={stream.events}
          trades={stream.trades}
          overlay={state?.overlay ?? null}
          warmupBars={state?.warmup_bars ?? session.warmup_bars}
          hasStrategy={hasStrategy}
          symbol={symbol}
        />
      </PanelCard>
    </div>
  );
}

export default function ReplayPage() {
  const create = useCreateReplaySession();
  const [active, setActive] = useState<Active | null>(null);
  const [lastBody, setLastBody] = useState<ReplaySessionIn | null>(null);
  const [lastSymbol, setLastSymbol] = useState<string | undefined>(undefined);

  const start = useCallback(
    (body: ReplaySessionIn, instrument: Instrument, version: StrategyVersion | null) => {
      setLastBody(body);
      setLastSymbol(instrument.symbol);
      create.mutate(body, { onSuccess: (s) => setActive({ session: s, instrument, version }) });
    },
    [create],
  );

  if (active) {
    return <ActiveReplay key={active.session.session_id} active={active} onEnd={() => setActive(null)} />;
  }

  return (
    <div className="grid grid-cols-12 gap-3">
      <PanelCard
        title={<span className="flex items-center gap-2">Historical replay <ReplayTag /></span>}
        subtitle="Stored 1-minute candles, one trading day, bar by bar"
        className="col-span-12 xl:col-span-4"
      >
        <ReplaySetupForm onStart={start} isPending={create.isPending} error={create.error} />
      </PanelCard>
      <div className="col-span-12 flex flex-col gap-3 xl:col-span-8">
        {create.error ? (
          <PanelCard title="Could not start" bodyClassName="p-3">
            <CreateError error={create.error} body={lastBody} symbol={lastSymbol} />
            {create.error instanceof ApiRequestError && create.error.status === 404 && (
              <p className="mt-2 text-[12px] text-text-3">
                <Link href="/market" className="text-accent-cyan">Open Market</Link> to see data coverage per instrument and timeframe.
              </p>
            )}
          </PanelCard>
        ) : (
          <PanelCard title="How replay works" bodyClassName="p-3">
            <ul className="flex flex-col gap-1.5 text-[12px] text-text-2">
              <li>The API loads the day&apos;s stored 1-minute candles and streams them at the chosen speed; nothing is fetched from a broker and nothing is simulated beyond what is stored.</li>
              <li>With a strategy version attached, the strategy engine, risk engine and execution simulator run in memory on ₹1,00,000 of virtual capital. Orders fill at the next bar&apos;s open with spread-aware slippage, exactly as in backtests and paper trading.</li>
              <li>Step backwards or seek: the session is rebuilt deterministically from the start, so the same day with the same seed always produces the same trades.</li>
              <li>Sessions live only in the API process and are deleted when you end them, leave the page or stay idle.</li>
            </ul>
          </PanelCard>
        )}
        <ExistingSessions
          current={null}
          onResume={(s) => setActive({ session: s, instrument: null, version: null })}
        />
      </div>
    </div>
  );
}
