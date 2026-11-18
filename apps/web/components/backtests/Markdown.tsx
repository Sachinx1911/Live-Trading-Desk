"use client";

import { parseMarkdown } from "@/lib/backtest-utils";
import { cn } from "@/lib/utils";

/** Minimal renderer for the deterministic backtest report (headings, lists, tables, code). */
export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks = parseMarkdown(text);
  return (
    <div className={cn("flex flex-col gap-2 text-xs text-text-1", className)}>
      {blocks.map((b, i) => {
        if (b.kind === "h") {
          const size = b.level <= 1 ? "text-base" : b.level === 2 ? "text-sm" : "text-xs uppercase tracking-wide text-text-2";
          return <p key={i} className={cn("mt-2 font-semibold", size)}>{b.text}</p>;
        }
        if (b.kind === "ul") return <ul key={i} className="list-disc pl-5 text-text-2">{b.items.map((it, j) => <li key={j}>{it}</li>)}</ul>;
        if (b.kind === "code") return <pre key={i} className="overflow-x-auto rounded-sm bg-raised p-2 font-mono text-[11px]">{b.text}</pre>;
        if (b.kind === "table")
          return (
            <table key={i} className="w-full text-[11px]">
              <thead className="text-[10px] uppercase tracking-wide text-text-3"><tr>{b.header.map((h, j) => <th key={j} className="border-b border-border px-2 py-1 text-left font-medium">{h}</th>)}</tr></thead>
              <tbody>{b.rows.map((r, j) => <tr key={j} className="border-b border-border/60">{r.map((c, k) => <td key={k} className="px-2 py-1 tabular">{c}</td>)}</tr>)}</tbody>
            </table>
          );
        return <p key={i} className="text-text-2">{b.text}</p>;
      })}
    </div>
  );
}
