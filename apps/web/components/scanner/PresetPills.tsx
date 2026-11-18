"use client";

import { Bookmark } from "lucide-react";
import type { SavedScan } from "@/lib/api/generated";
import { cn } from "@/lib/utils";

/** 28px pill row (TradingView screener presets): selected = raised chrome + primary text. */
export function PresetPills({
  presets,
  saved,
  activeId,
  onPick,
}: {
  presets: SavedScan[];
  saved: SavedScan[];
  activeId: number | null;
  onPick: (s: SavedScan | null) => void;
}) {
  const pill = (s: SavedScan | null, label: string, icon?: boolean) => {
    const active = (s?.id ?? null) === activeId;
    return (
      <button
        key={s?.id ?? "all"}
        type="button"
        title={s?.description ?? undefined}
        onClick={() => onPick(s)}
        className={cn(
          "inline-flex h-7 shrink-0 items-center gap-1 rounded-[var(--r-pill)] border px-3 text-[13px] whitespace-nowrap transition-colors",
          active ? "border-transparent bg-raised font-semibold text-text-1" : "border-border text-text-2 hover:bg-row-hover hover:text-text-1",
        )}
      >
        {icon && <Bookmark className="size-3" />}
        {label}
      </button>
    );
  };
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:thin]">
      {pill(null, "All instruments")}
      {presets.map((p) => pill(p, p.name))}
      {saved.length > 0 && <span className="mx-1 h-4 w-px shrink-0 bg-border" />}
      {saved.map((s) => pill(s, s.name, true))}
    </div>
  );
}
