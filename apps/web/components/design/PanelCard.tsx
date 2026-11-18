import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Flat black pane (reference §2/§5): no radius, a 1px #303030 edge, a 28px header with a
 * 1px divider, 600-weight title. Panels separate by tone and hairlines, never by shadows.
 */
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
    <section className={cn("flex min-w-0 flex-col overflow-hidden border border-border bg-pane", className)}>
      {banner}
      {(title || actions) && (
        <header className="flex min-h-7 items-center justify-between gap-2 border-b border-border px-3">
          <div className="flex min-w-0 items-baseline gap-2 py-1">
            {title && <h2 className="truncate text-[14px] font-semibold text-text-1">{title}</h2>}
            {subtitle && <p className="truncate text-[12px] text-text-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2 py-1">{actions}</div>}
        </header>
      )}
      <div className={cn("flex-1 p-3", bodyClassName)}>{children}</div>
    </section>
  );
}
