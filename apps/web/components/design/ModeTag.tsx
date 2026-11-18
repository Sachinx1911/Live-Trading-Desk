import { cn } from "@/lib/utils";

export type TradingMode = "paper" | "live";

/* 20px pills, 11px uppercase: paper = accent tint, live = down tint, AI = purple tint. */
export function ModeTag({ mode, className }: { mode: TradingMode; className?: string }) {
  const live = mode === "live";
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full px-2 text-[11px] font-semibold uppercase tracking-wide",
        live ? "bg-down-soft text-down" : "bg-accent-soft text-accent-text",
        className,
      )}
      aria-label={`${live ? "Live" : "Paper"} trading`}
    >
      {live ? "Live" : "Paper"}
    </span>
  );
}

export function AiBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full bg-ai-soft px-2 text-[11px] font-semibold uppercase tracking-wide text-ai",
        className,
      )}
    >
      AI
    </span>
  );
}
