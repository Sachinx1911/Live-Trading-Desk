"use client";

import { PictureInPicture2 } from "lucide-react";
import { getPanel, panelUrl, type PanelId } from "@/lib/panels";
import { cn } from "@/lib/utils";

/**
 * Small "Open as panel" icon for full pages (Stage 4.4): pops the same view out as a
 * chrome-less, read-only panel window at the panel's preferred size. A plain link underneath,
 * so a middle-click or a blocked pop-up still opens it in a tab.
 */
export function OpenAsPanel({
  panel,
  params,
  className,
}: {
  panel: PanelId;
  params?: Record<string, string | number | boolean | null | undefined>;
  className?: string;
}) {
  const href = panelUrl(panel, params);
  const def = getPanel(panel);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener"
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        const [w, h] = def.size.preferred;
        const win = window.open(href, `panel-${panel}`, `popup,width=${w},height=${h}`);
        if (win) e.preventDefault();
      }}
      className={cn(
        "inline-flex size-6 shrink-0 items-center justify-center rounded-[var(--r-sm)] text-text-3 hover:bg-raised hover:text-accent-text",
        className,
      )}
      title={`Open as panel (${def.title})`}
      aria-label={`Open ${def.title} as a panel window`}
    >
      <PictureInPicture2 className="size-3.5" aria-hidden />
    </a>
  );
}
