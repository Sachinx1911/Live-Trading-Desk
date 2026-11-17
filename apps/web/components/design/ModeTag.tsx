import { cn } from "@/lib/utils";

export type TradingMode = "paper" | "live";

export function ModeTag({ mode, className }: { mode: TradingMode; className?: string }) {
  const live = mode === "live";
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-sm border px-1.5 text-[11px] font-semibold uppercase tracking-wide",
        live
          ? "border-mode-live/40 bg-mode-live/10 text-mode-live"
          : "border-mode-paper/40 bg-mode-paper/10 text-mode-paper",
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
        "inline-flex h-5 items-center rounded-sm border border-ai/40 bg-ai/10 px-1.5 text-[11px] font-semibold uppercase tracking-wide text-ai",
        className,
      )}
    >
      AI
    </span>
  );
}
