"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ThemePreference } from "@/lib/theme";

interface UiState {
  /** true = 52px icon rail (default), false = 220px rail with labels. */
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  /** Theme preference; "system" follows prefers-color-scheme. Dark is the default. */
  theme: ThemePreference;
  setTheme: (t: ThemePreference) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: true,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      theme: "dark",
      setTheme: (theme) => set({ theme }),
    }),
    { name: "tp.ui", version: 3 },
  ),
);
