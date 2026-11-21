"use client";

import { AppWindow, Lock } from "lucide-react";
import { useEffect } from "react";
import { DataStateBadge, EmptyState } from "@/components/design";
import type { Freshness } from "@/lib/api/generated";
import { getPanel, type PanelId, type PanelParamError } from "@/lib/panels";
import { cn } from "@/lib/utils";

/**
 * Chrome-less panel window (Mark 1 Stage 4.4): a thin HUD header and a body that fills the
 * window. The header always carries the data state (CLAUDE.md rule 5: Live / Delayed /
 * Disconnected / Demo / Historical) and where the data comes from. Panels are read-only; the
 * only link goes to the full page in the main app window.
 */
export function PanelFrame({
  panel,
  subtitle,
  state,
  stateDetail,
  source,
  fullHref,
  children,
  bodyClassName,
}: {
  panel: PanelId;
  /** Parameters in human form, e.g. "NIFTY · 5m". */
  subtitle?: string;
  /** Omitted while the panel cannot say yet (loading or invalid parameters). */
  state?: Freshness;
  stateDetail?: string;
  source?: string;
  /** Full app page; opened in the main window ("tp-main"). */
  fullHref?: string;
  children: React.ReactNode;
  bodyClassName?: string;
}) {
  const def = getPanel(panel);
  useEffect(() => {
    document.title = `${def.title}${subtitle ? ` · ${subtitle}` : ""} — panel`;
  }, [def.title, subtitle]);

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-app">
      <header className="@container flex h-8 shrink-0 items-center gap-2 border-b border-border bg-pane px-2.5 shadow-[var(--glow)]">
        <span className="relative flex size-3 shrink-0 items-center justify-center rounded-full border border-accent/70" aria-hidden>
          <span className="size-1 rounded-full bg-accent" />
        </span>
        <h1 className="hud-label shrink-0 text-amber">{def.title}</h1>
        {subtitle && <p className="min-w-0 truncate font-mono text-[11px] text-text-2">{subtitle}</p>}
        <div className="ml-auto flex min-w-0 shrink-0 items-center gap-2">
          {source && <span className="hidden truncate font-mono text-[10px] uppercase tracking-wide text-text-3 @xl:inline">src {source}</span>}
          <span className="hidden items-center gap-1 text-[10px] uppercase tracking-wide text-text-3 @2xl:inline-flex" title="Panels only show data; actions stay in the app">
            <Lock className="size-2.5" aria-hidden /> read-only
          </span>
          {state && <DataStateBadge state={state} detail={stateDetail} />}
          {fullHref && (
            <a
              href={fullHref}
              target="tp-main"
              className="flex size-6 items-center justify-center rounded-[var(--r-sm)] text-text-3 hover:bg-raised hover:text-accent-text"
              title="Open the full page in the app"
              aria-label="Open the full page in the app"
            >
              <AppWindow className="size-3.5" />
            </a>
          )}
        </div>
      </header>
      <main className={cn("relative min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</main>
    </div>
  );
}

/** Invalid or missing parameters: names each one; never renders an invented panel. */
export function PanelParamErrors({ panel, errors }: { panel: PanelId; errors: PanelParamError[] }) {
  const def = getPanel(panel);
  return (
    <div className="flex h-full items-center justify-center p-4">
      <div className="hud-panel hud-frame w-full max-w-xl rounded-[var(--r-sm)] border border-down/50 bg-pane p-4">
        <p className="hud-label text-down">Panel parameters</p>
        <ul className="mt-2 flex flex-col gap-1 text-[13px]">
          {errors.map((e) => (
            <li key={e.param}>
              <code className="font-mono text-amber">{e.param}</code> <span className="text-text-2">{e.message}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 font-mono text-[11px] break-all text-text-3">expected {def.path}</p>
      </div>
    </div>
  );
}

/** Honest empty / error state inside a panel body. */
export function PanelMessage({ title, description, tone = "muted" }: { title: string; description?: string; tone?: "muted" | "error" }) {
  return (
    <div className="flex h-full items-center justify-center p-4">
      <EmptyState
        title={title}
        description={description}
        className={cn("h-auto max-w-xl flex-none", tone === "error" && "border-down/50 [&_p:first-of-type]:text-down")}
      />
    </div>
  );
}
