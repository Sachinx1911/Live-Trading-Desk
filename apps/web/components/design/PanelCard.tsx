import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Compact information panel: 12px padding, 1px subtle border, 6px radius (page map §1.4). */
export function PanelCard({
  title,
  subtitle,
  actions,
  banner,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Rendered above the header, e.g. <DemoBanner />. */
  banner?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn(
        "flex min-w-0 flex-col overflow-hidden rounded-md border border-border-subtle bg-panel",
        className,
      )}
    >
      {banner}
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
          <div className="min-w-0">
            {title && (
              <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-text-secondary">
                {title}
              </h2>
            )}
            {subtitle && <p className="truncate text-[11px] text-text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("flex-1 p-3", bodyClassName)}>{children}</div>
    </section>
  );
}
