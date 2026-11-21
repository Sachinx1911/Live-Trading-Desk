import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * HUD panel (references/design-reference-images.md): navy pane with a thin cyan hairline,
 * bracketed corners and a soft glow; the header is a monospaced uppercase label in amber
 * (references: amber for headers). Unfolds in under 0.3 s; no motion with reduced-motion.
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
    <section
      className={cn(
        "hud-panel hud-frame hud-glow flex min-w-0 flex-col overflow-hidden rounded-[var(--r-sm)] border border-border bg-pane",
        className,
      )}
    >
      {banner}
      {(title || actions) && (
        <header className="flex min-h-8 items-center justify-between gap-2 border-b border-border px-3">
          <div className="flex min-w-0 items-baseline gap-2 py-1">
            {title && <h2 className="hud-label truncate text-amber">{title}</h2>}
            {subtitle && <p className="truncate text-[12px] text-text-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2 py-1">{actions}</div>}
        </header>
      )}
      <div className={cn("flex-1 p-3", bodyClassName)}>{children}</div>
    </section>
  );
}
