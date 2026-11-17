import type { LucideIcon } from "lucide-react";
import { Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  icon: Icon = Hourglass,
  className,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full min-h-24 flex-col items-center justify-center gap-1.5 rounded-sm border border-dashed border-border-subtle px-4 py-6 text-center",
        className,
      )}
    >
      <Icon className="size-4 text-text-muted" aria-hidden />
      <p className="text-xs font-medium text-text-secondary">{title}</p>
      {description && <p className="max-w-64 text-[11px] text-text-muted">{description}</p>}
    </div>
  );
}

/** Standard placeholder for a feature that lands in a later phase. */
export function PhasePlaceholder({ phase, what }: { phase: number; what?: string }) {
  return (
    <EmptyState
      title={`Not available until Phase ${phase}`}
      description={what ? `${what} ships in Phase ${phase}. Nothing is simulated here.` : undefined}
    />
  );
}
