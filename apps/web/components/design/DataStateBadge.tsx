"use client";

import { Clock, FlaskConical, Radio, TimerOff, Unplug, WifiOff } from "lucide-react";
import type { Freshness } from "@/lib/api/generated";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const CONFIG: Record<
  Freshness,
  { label: string; dot: string; text: string; Icon: typeof Radio; help: string; pulse?: boolean }
> = {
  live: {
    label: "Live",
    dot: "bg-state-live",
    text: "text-state-live",
    Icon: Radio,
    help: "Streaming from a connected provider; last event under 5 seconds old.",
    pulse: true,
  },
  delayed: {
    label: "Delayed",
    dot: "bg-state-delayed",
    text: "text-state-delayed",
    Icon: Clock,
    help: "Last event is 5–120 seconds old, or the provider marks this feed as delayed.",
  },
  stale: {
    label: "Stale",
    dot: "bg-state-stale",
    text: "text-state-stale",
    Icon: TimerOff,
    help: "No update for more than 2 minutes. Values are shown greyed with their last-seen time.",
  },
  disconnected: {
    label: "Disconnected",
    dot: "bg-state-disconnected",
    text: "text-state-disconnected",
    Icon: WifiOff,
    help: "No feed: provider down, token expired or not configured. Nothing here is current.",
  },
  demo: {
    label: "Demo",
    dot: "bg-state-demo",
    text: "text-state-demo",
    Icon: FlaskConical,
    help: "Synthetic data from the fake provider. Never real money, never a real price.",
  },
  historical: {
    label: "Historical",
    dot: "bg-state-historical",
    text: "text-state-historical",
    Icon: Unplug,
    help: "Stored values from a backtest or replay context, not a live feed.",
  },
};

export function DataStateBadge({
  state,
  detail,
  className,
}: {
  state: Freshness;
  /** Short suffix such as the age ("12s") or a reason. */
  detail?: string;
  className?: string;
}) {
  const c = CONFIG[state];
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            className={cn(
              "inline-flex h-5 items-center gap-1.5 rounded-sm border border-border-subtle bg-panel-raised px-1.5 text-[11px] font-medium uppercase tracking-wide",
              c.text,
              className,
            )}
            aria-label={`Data state: ${c.label}${detail ? ` (${detail})` : ""}`}
          />
        }
      >
        <span className="relative flex size-1.5">
          {c.pulse && (
            <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", c.dot)} />
          )}
          <span className={cn("relative size-1.5 rounded-full", c.dot)} />
        </span>
        {c.label}
        {detail && <span className="normal-case tracking-normal text-text-secondary">{detail}</span>}
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-64 text-xs">
        {c.help}
      </TooltipContent>
    </Tooltip>
  );
}

/** Full-width striped banner used across the top of any panel showing demo data. */
export function DemoBanner() {
  return (
    <div className="demo-stripes flex items-center gap-2 border-b border-border-subtle px-3 py-1 text-[11px] font-semibold tracking-wide text-ai">
      <FlaskConical className="size-3" /> DEMO DATA
    </div>
  );
}
