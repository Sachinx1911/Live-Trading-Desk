import { formatMoney, formatPct, formatSignedMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Numeric display primitives. `value` null/undefined renders an em-dash: there is no such
 * thing as a default zero in this UI (page map §1.5).
 */

function pnlClass(v: number | null | undefined, muted?: boolean) {
  if (muted || v == null || v === 0) return "text-text-2";
  return v > 0 ? "text-up" : "text-down";
}

export function Money({
  value,
  currency = "INR",
  signed = false,
  whole = false,
  muted = false,
  className,
}: {
  value: number | null | undefined;
  currency?: string;
  signed?: boolean;
  whole?: boolean;
  muted?: boolean;
  className?: string;
}) {
  if (value == null) return <span className={cn("tabular text-text-3", className)}>—</span>;
  const text = signed ? formatSignedMoney(value, currency) : formatMoney(value, { currency, whole });
  return (
    <span className={cn("tabular", signed ? pnlClass(value, muted) : muted && "text-text-2", className)}>
      {text}
    </span>
  );
}

export function Pct({
  value,
  digits = 2,
  signed = true,
  muted = false,
  className,
}: {
  value: number | null | undefined;
  digits?: number;
  signed?: boolean;
  muted?: boolean;
  className?: string;
}) {
  if (value == null) return <span className={cn("tabular text-text-3", className)}>—</span>;
  return (
    <span className={cn("tabular", signed ? pnlClass(value, muted) : "", className)}>
      {formatPct(value, digits, signed)}
    </span>
  );
}

export function Dash({ className }: { className?: string }) {
  return <span className={cn("tabular text-text-3", className)}>—</span>;
}
