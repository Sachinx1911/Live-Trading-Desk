import type { CurvePoint } from "@/lib/api/generated";

export interface Point {
  ts: string;
  value: number;
}

/** Normalise `[ts, v]` tuples or `{ts, equity|value|drawdown|...}` objects into points. */
export function normaliseCurve(curve: CurvePoint[] | undefined | null, preferredKeys = ["equity", "value", "drawdown", "dd", "y"]): Point[] {
  if (!curve) return [];
  const out: Point[] = [];
  for (const p of curve) {
    if (Array.isArray(p)) {
      const v = Number(p[1]);
      if (p[0] && Number.isFinite(v)) out.push({ ts: String(p[0]), value: v });
      continue;
    }
    if (p && typeof p === "object" && "ts" in p) {
      for (const k of preferredKeys) {
        const raw = (p as Record<string, unknown>)[k];
        if (raw != null) {
          const v = Number(raw);
          if (Number.isFinite(v)) out.push({ ts: String(p.ts), value: v });
          break;
        }
      }
    }
  }
  return out;
}

/** Ratio-style metrics are shown as fractions or percents depending on magnitude guesswork
 *  being wrong; the backend reports percentages for *_pct and win_rate, fractions otherwise. */
export function metricNumber(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

const COMPARE_KEY = "tp.backtest.compare";

export function readCompareList(): number[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(COMPARE_KEY);
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(arr) ? arr.filter((x): x is number => typeof x === "number") : [];
  } catch {
    return [];
  }
}

export function writeCompareList(ids: number[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(COMPARE_KEY, JSON.stringify(Array.from(new Set(ids))));
  window.dispatchEvent(new Event("tp-compare-changed"));
}

/** Tiny markdown → HTML-ish React structure (headings, paragraphs, lists, tables, code). */
export type MdBlock =
  | { kind: "h"; level: number; text: string }
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "code"; text: string };

export function parseMarkdown(md: string): MdBlock[] {
  const lines = md.replace(/\r/g, "").split("\n");
  const blocks: MdBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i++;
      continue;
    }
    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      blocks.push({ kind: "code", text: buf.join("\n") });
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      blocks.push({ kind: "h", level: h[1].length, text: h[2] });
      i++;
      continue;
    }
    if (line.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      if (rows.length) blocks.push({ kind: "table", header: rows[0], rows: rows.slice(1) });
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      blocks.push({ kind: "ul", items });
      continue;
    }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^(#{1,6})\s/.test(lines[i]) && !lines[i].trim().startsWith("|") && !/^\s*[-*]\s+/.test(lines[i]) && !lines[i].startsWith("```")) buf.push(lines[i++]);
    blocks.push({ kind: "p", text: buf.join(" ") });
  }
  return blocks;
}

// ---------------------------------------------------------------- compare list as an external store
import { useSyncExternalStore } from "react";

let cachedRaw = "";
let cachedList: number[] = [];

function snapshot(): number[] {
  const raw = typeof window === "undefined" ? "" : (window.localStorage.getItem(COMPARE_KEY) ?? "");
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedList = readCompareList();
  }
  return cachedList;
}

const EMPTY: number[] = [];

function subscribe(cb: () => void) {
  window.addEventListener("tp-compare-changed", cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener("tp-compare-changed", cb);
    window.removeEventListener("storage", cb);
  };
}

/** Reactive view of the compare list (localStorage), safe during hydration. */
export function useCompareList(): number[] {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY);
}
