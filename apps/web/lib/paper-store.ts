"use client";

import { create } from "zustand";

const KEY = "tp.paper.account";

/** Which paper account the paper pages, dashboard and risk settings are looking at. */
interface PaperSelection {
  accountId: number | null;
  select: (id: number | null) => void;
}

function initial(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(KEY);
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) ? n : null;
}

export const usePaperSelection = create<PaperSelection>((set) => ({
  accountId: initial(),
  select: (id) => {
    if (typeof window !== "undefined") {
      if (id == null) window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, String(id));
    }
    set({ accountId: id });
  },
}));
