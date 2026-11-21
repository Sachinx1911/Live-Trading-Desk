"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { Instrument } from "@/lib/api/generated";
import { parsePanelParams, type PanelId } from "@/lib/panels";

/** The panel's query string, validated against lib/panels.ts. */
export function usePanelParams(id: PanelId) {
  const search = useSearchParams();
  const key = search.toString();
  return useMemo(() => parsePanelParams(id, new URLSearchParams(key)), [id, key]);
}

/**
 * Resolve an NSE symbol to an instrument the same way the market pages do (index first, then
 * the exact symbol). `null` data = the instrument master has no such symbol.
 */
export function useInstrumentBySymbol(symbol: string | undefined) {
  return useQuery({
    queryKey: ["instruments", "by-symbol", symbol ?? ""],
    queryFn: async () => {
      const hits = await api<Instrument[]>(`/instruments?q=${encodeURIComponent(symbol!)}&exchange=NSE&limit=20`);
      return hits.find((i) => i.symbol === symbol && i.segment === "index") ?? hits.find((i) => i.symbol === symbol) ?? null;
    },
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

/** Today's date in IST (YYYY-MM-DD). */
export function istToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

/** Content-box size of an element, kept current with a ResizeObserver (0×0 before mount). */
export function useElementSize<T extends HTMLElement>(): [React.RefCallback<T>, { width: number; height: number }] {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const roRef = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    roRef.current?.disconnect();
    roRef.current = null;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setSize((s) => (s.width === Math.round(width) && s.height === Math.round(height) ? s : { width: Math.round(width), height: Math.round(height) }));
    });
    ro.observe(el);
    roRef.current = ro;
  }, []);
  return [ref, size];
}
