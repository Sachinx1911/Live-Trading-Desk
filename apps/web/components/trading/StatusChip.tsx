import { cn } from "@/lib/utils";

type Tone = "ok" | "warn" | "bad" | "muted" | "info" | "ai";

const TONES: Record<Tone, string> = {
  ok: "border-up/40 bg-up/10 text-up",
  warn: "border-warn/40 bg-warn/10 text-warn",
  bad: "border-down/40 bg-down/10 text-down",
  muted: "border-border bg-raised text-text-2",
  info: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  ai: "border-ai/40 bg-ai/10 text-ai",
};

const STATUS_TONE: Record<string, Tone> = {
  // activations
  active: "ok",
  paused: "warn",
  stopped: "muted",
  // orders
  intent: "muted",
  submitted: "info",
  open: "info",
  partially_filled: "warn",
  filled: "ok",
  cancelled: "muted",
  rejected: "bad",
  broker_rejected: "bad",
  unknown: "warn",
  // strategy versions
  draft: "muted",
  backtested: "info",
  validated: "info",
  paper: "warn",
  approved_live: "ok",
  retired: "muted",
  // sides
  buy: "ok",
  sell: "bad",
};

export function StatusChip({ value, tone, className }: { value: string; tone?: Tone; className?: string }) {
  const t = tone ?? STATUS_TONE[value] ?? "muted";
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-sm border px-1.5 text-[11px] font-semibold uppercase tracking-wide",
        TONES[t],
        className,
      )}
    >
      {value.replace(/_/g, " ")}
    </span>
  );
}

export function SideText({ side }: { side: "buy" | "sell" }) {
  return (
    <span className={cn("font-semibold uppercase", side === "buy" ? "text-up" : "text-down")}>
      {side}
    </span>
  );
}
