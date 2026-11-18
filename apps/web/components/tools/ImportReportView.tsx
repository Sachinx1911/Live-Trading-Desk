"use client";

import { AlertTriangle } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ImportReport } from "@/lib/api/generated";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

function Stat({ label, value, tone }: { label: string; value: number; tone?: "ok" | "bad" }) {
  return (
    <div className="flex flex-col border border-border bg-raised px-3 py-2">
      <span className="text-[11px] uppercase tracking-wide text-text-3">{label}</span>
      <span className={cn("text-[18px] font-semibold tabular", tone === "ok" && "text-up", tone === "bad" && value > 0 && "text-down")}>{formatNumber(value)}</span>
    </div>
  );
}

export function ImportReportView({ report }: { report: ImportReport }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Rows read" value={report.rows_read} />
        <Stat label="Accepted" value={report.rows_accepted} tone="ok" />
        <Stat label="Rejected" value={report.rows_rejected} tone="bad" />
      </div>

      {report.warnings.length > 0 && (
        <ul className="flex flex-col gap-1 border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
          {report.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {w}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-1">
        <h3 className="text-[12px] font-semibold text-text-2">Coverage</h3>
        {report.coverage.length === 0 ? (
          <p className="text-xs text-text-3">No accepted rows, so nothing to cover.</p>
        ) : (
          <Table dense>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>First bar (IST)</TableHead>
                <TableHead>Last bar (IST)</TableHead>
                <TableHead className="text-right">Bars</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.coverage.map((c) => (
                <TableRow key={c.symbol}>
                  <TableCell className="font-medium">{c.symbol}</TableCell>
                  <TableCell className="tabular text-text-2">{formatDateTime(c.first_ts)}</TableCell>
                  <TableCell className="tabular text-text-2">{formatDateTime(c.last_ts)}</TableCell>
                  <TableCell className="text-right tabular">{formatNumber(c.count)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {report.rows_rejected > 0 && (
        <div className="flex flex-col gap-1">
          <h3 className="text-[12px] font-semibold text-text-2">
            Rejections{report.rejections.length < report.rows_rejected && <span className="ml-1 font-normal text-text-3">(first {report.rejections.length} of {formatNumber(report.rows_rejected)})</span>}
          </h3>
          <Table dense>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">Row</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Sample</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.rejections.map((r, i) => (
                <TableRow key={`${r.row}-${i}`}>
                  <TableCell className="text-right tabular">{r.row}</TableCell>
                  <TableCell className="whitespace-normal text-down">{r.reason}</TableCell>
                  <TableCell className="max-w-96 truncate font-mono text-[11px] text-text-3" title={JSON.stringify(r.sample)}>
                    {JSON.stringify(r.sample)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <p className="font-mono text-[11px] text-text-3">content sha256 {report.content_hash.slice(0, 16)}… · source {report.source_type}</p>
    </div>
  );
}
