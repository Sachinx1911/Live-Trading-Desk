import { cn } from "@/lib/utils";

const STYLE: Record<string, string> = {
  green: "border-up/50 text-up",
  yellow: "border-warn/50 text-warn",
  red: "border-down/60 text-down",
};

/** Plan §2.3 risk level of an action: green read-only, yellow change, red money/safety. */
export function RiskBadge({ risk, className }: { risk: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-4 items-center rounded-full border px-1.5 font-mono text-[10px] uppercase leading-none",
        STYLE[risk] ?? "border-border text-text-3",
        className,
      )}
      title={`risk: ${risk}`}
    >
      {risk}
    </span>
  );
}
