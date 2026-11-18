"use client";

import { useEffect } from "react";
import { useUiStore } from "@/components/layout/ui-store";
import { applyTheme, resolveTheme, watchSystemTheme } from "@/lib/theme";

/** Keeps <html data-theme> in sync with the persisted preference and the OS setting. */
export function ThemeSync() {
  const pref = useUiStore((s) => s.theme);
  useEffect(() => {
    applyTheme(resolveTheme(pref));
    if (pref !== "system") return;
    return watchSystemTheme(() => applyTheme(resolveTheme("system")));
  }, [pref]);
  return null;
}
