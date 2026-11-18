"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useUiStore } from "@/components/layout/ui-store";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import type { ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/utils";

export const THEME_OPTIONS: { value: ThemePreference; label: string; Icon: typeof Sun }[] = [
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "light", label: "Light", Icon: Sun },
  { value: "system", label: "System", Icon: Monitor },
];

/** Radio items for the top-bar user menu. */
export function ThemeMenuItems() {
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  return (
    <DropdownMenuGroup>
      <DropdownMenuLabel className="text-[11px] uppercase tracking-wide text-text-3">Theme</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as ThemePreference)}>
        {THEME_OPTIONS.map(({ value, label, Icon }) => (
          <DropdownMenuRadioItem key={value} value={value}>
            <Icon className="size-3.5" /> {label}
          </DropdownMenuRadioItem>
        ))}
      </DropdownMenuRadioGroup>
    </DropdownMenuGroup>
  );
}

/** Segmented pill control for settings pages. */
export function ThemeSegmented({ className }: { className?: string }) {
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  return (
    <div className={cn("inline-flex items-center gap-1 rounded-[var(--r-pill)] bg-raised p-0.5", className)} role="radiogroup" aria-label="Theme">
      {THEME_OPTIONS.map(({ value, label, Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(value)}
            className={cn(
              "inline-flex h-6 items-center gap-1.5 rounded-[var(--r-pill)] px-3 text-[13px] transition-colors",
              active ? "bg-selected text-on-selected" : "text-text-2 hover:text-text-1",
            )}
          >
            <Icon className="size-3.5" aria-hidden /> {label}
          </button>
        );
      })}
    </div>
  );
}
