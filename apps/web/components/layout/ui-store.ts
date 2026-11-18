"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  /** true = 52px icon rail (default), false = 220px rail with labels. */
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: true,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    { name: "tp.ui", version: 2 },
  ),
);
