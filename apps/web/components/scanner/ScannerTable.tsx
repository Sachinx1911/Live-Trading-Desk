"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { EmptyState } from "@/components/design";
import { Pill } from "@/components/market/RegimeBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ScanField, ScanRow, ScanSort } from "@/lib/api/generated";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEGMENT_CLS: Record<string, string> = { equity: "bg-raised text-text-2", index: "bg-accent-soft text-accent-text", futures: "bg-warn-soft text-warn" };
const TREND_CLS: Record<string, string> = { up: "bg-up-soft text-up", down: "bg-down-soft text-down", sideways: "bg-raised text-text-3" };
const VOL_CLS: Record<string, string> = { low: "bg-accent-soft text-accent-text", normal: "bg-raised text-text-2", high: "bg-warn-soft text-warn" };
const STRUCT_CLS: Record<string, string> = { bullish: "bg-raised text-up", bearish: "bg-raised text-down", range: "bg-raised text-text-3" };
const ALIGN_CLS: Record<string, string> = { bull: "bg-up-soft text-up", bear: "bg-down-soft text-down", mixed: "bg-raised text-text-3" };

function compact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e7) return `${formatNumber(v / 1e7, 2)} Cr`;
  if (a >= 1e5) return `${formatNumber(v / 1e5, 2)} L`;
  return formatNumber(v, 0);
}

/** Cell renderer: colour only where it carries meaning (sign, overbought/oversold, regime). */
function cell(f: ScanField | undefined, name: string, v: string | number | boolean | null): ReactNode {
  if (v == null) return <span className="text-text-3">—</span>;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (name === "segment") return <Pill className={SEGMENT_CLS[String(v)] ?? "bg-raised text-text-3"}>{String(v)}</Pill>;
  if (name === "regime_trend") return <Pill className={TREND_CLS[String(v)] ?? "bg-raised text-text-3"}>{String(v)}</Pill>;
  if (name === "regime_volatility") return <Pill className={VOL_CLS[String(v)] ?? "bg-raised text-text-3"}>{String(v)} vol</Pill>;
  if (name === "regime_structure") return <Pill className={STRUCT_CLS[String(v)] ?? "bg-raised text-text-3"}>{String(v)}</Pill>;
  if (name === "ema_alignment") return <Pill className={ALIGN_CLS[String(v)] ?? "bg-raised text-text-3"}>{String(v)}</Pill>;
  if (typeof v !== "number") return String(v);
  if (name === "rsi14") return <span className={cn(v >= 70 ? "text-down" : v <= 30 ? "text-up" : undefined)}>{formatNumber(v, 1)}</span>;
  if (f?.type === "percent") {
    const signed = name.startsWith("change") || name.startsWith("gap") || name.startsWith("oi_change");
    const cls = signed ? (v > 0 ? "text-up" : v < 0 ? "text-down" : "text-text-3") : undefined;
    return <span className={cls}>{signed && v > 0 ? "+" : ""}{formatNumber(v, 2)}%</span>;
  }
  if (name === "volume" || name === "avg_volume_20" || name === "oi") return compact(v);
  if (name === "lot_size" || name === "bars") return formatNumber(v, 0);
  return formatNumber(v, 2);
}

export function ScannerTable({
  columns,
  rows,
  fields,
  sort,
  onSort,
  loading,
}: {
  columns: string[];
  rows: ScanRow[];
  fields: Map<string, ScanField>;
  sort: ScanSort | null;
  onSort: (s: ScanSort | null) => void;
  loading: boolean;
}) {
  const router = useRouter();
  const cols = columns.filter((c) => c !== "symbol" && c !== "name");
  const numeric = (c: string) => {
    const t = fields.get(c)?.type;
    return t === "number" || t === "percent";
  };
  const head = (c: string, label: string, right: boolean) => {
    const active = sort?.field === c;
    return (
      <TableHead
        key={c}
        className={cn("cursor-pointer select-none whitespace-nowrap hover:text-text-1", right && "text-right")}
        onClick={() => onSort(active ? (sort.dir === "desc" ? { field: c, dir: "asc" } : null) : { field: c, dir: numeric(c) ? "desc" : "asc" })}
        title={fields.get(c)?.description ?? undefined}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active && (sort.dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
        </span>
      </TableHead>
    );
  };
  if (!loading && rows.length === 0) {
    return <EmptyState title="No instruments match" description="Loosen a filter or pick another preset." />;
  }
  return (
    <div className={cn("transition-opacity", loading && "opacity-60")}>
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-pane">
          <TableRow>
            {head("symbol", "Symbol", false)}
            {cols.map((c) => head(c, fields.get(c)?.label ?? c, numeric(c)))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.instrument_id} className="cursor-pointer" onClick={() => router.push(`/market?instrument=${r.instrument_id}`)}>
              <TableCell className="whitespace-nowrap">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-text-1">{String(r.symbol ?? "")}</span>
                  {columns.includes("name") && <span className="truncate text-[12px] text-text-3">{String(r.name ?? "")}</span>}
                </div>
              </TableCell>
              {cols.map((c) => (
                <TableCell key={c} className={cn("whitespace-nowrap", numeric(c) && "text-right tabular")}>
                  {cell(fields.get(c), c, r[c] ?? null)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
