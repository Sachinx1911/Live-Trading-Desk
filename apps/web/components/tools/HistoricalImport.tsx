"use client";

import { Database, FileUp, FlaskConical, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/lib/api/client";
import type { ImportMapping, ImportReport } from "@/lib/api/generated";
import { useUploadImport } from "@/lib/api/imports";
import { useMe } from "@/lib/api/queries";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ImportJobsTable } from "./ImportJobsTable";
import { ImportMappingForm } from "./ImportMappingForm";
import { ImportReportView } from "./ImportReportView";
import { autoMap, DEFAULT_MAPPING, mappingProblems, normaliseMapping, readCsvHeader } from "./importMapping";

const ACCEPT = ".csv,.txt,.parquet,.xlsx,.xls,.json";
const MAX_BYTES = 50 * 1024 * 1024;
/** A dry run is "clean enough" to commit when something was accepted and ≤5 % was rejected. */
const MAX_REJECT_RATIO = 0.05;

function fileKey(f: File): string {
  return `${f.name}:${f.size}:${f.lastModified}`;
}

function commitBlocker(report: ImportReport): string | null {
  if (report.rows_accepted === 0) return "Nothing was accepted; fix the mapping or the file first.";
  if (report.rows_rejected / Math.max(report.rows_read, 1) > MAX_REJECT_RATIO) {
    return `More than ${MAX_REJECT_RATIO * 100}% of rows were rejected; fix the file or mapping before committing.`;
  }
  return null;
}

export function HistoricalImport() {
  const me = useMe();
  const isOwner = me.data?.roles.includes("owner") ?? false;
  const upload = useUploadImport();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [mapping, setMapping] = useState<ImportMapping>(DEFAULT_MAPPING);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  // The report is only valid for the exact file + mapping it was produced from.
  const [dryRun, setDryRun] = useState<{ key: string; report: ImportReport } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [committed, setCommitted] = useState<{ jobId: number; rows: number } | null>(null);

  const normalised = normaliseMapping(mapping);
  const currentKey = file ? `${fileKey(file)}|${JSON.stringify(normalised)}` : "";
  const report = dryRun && dryRun.key === currentKey ? dryRun.report : null;
  const problems = mappingProblems(normalised);
  const blocker = report ? commitBlocker(report) : null;
  const canCommit = !!report && !blocker && isOwner && !upload.isPending;
  const apiError = upload.error instanceof ApiRequestError ? upload.error.message : upload.error ? "Cannot reach the API." : null;

  async function pickFile(f: File | null) {
    setDryRun(null);
    setConfirming(false);
    setCommitted(null);
    upload.reset();
    if (!f) {
      setFile(null);
      setColumns([]);
      return;
    }
    if (f.size > MAX_BYTES) {
      setFileError(`${f.name} is ${(f.size / 1024 / 1024).toFixed(1)} MB; the limit is 50 MB.`);
      return;
    }
    setFileError(null);
    setFile(f);
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (ext === "csv" || ext === "txt") {
      const header = await readCsvHeader(f);
      setColumns(header);
      setMapping((m) => autoMap(header, m));
    } else {
      setColumns([]); // binary formats: type column names by hand
    }
  }

  async function runDry() {
    if (!file) return;
    setConfirming(false);
    setCommitted(null);
    const res = await upload.mutateAsync({ file, mapping: normalised, commit: false });
    setDryRun({ key: currentKey, report: res.report });
  }

  async function runCommit() {
    if (!file || !canCommit) return;
    const res = await upload.mutateAsync({ file, mapping: normalised, commit: true });
    setConfirming(false);
    if (res.job) setCommitted({ jobId: res.job.id, rows: res.job.rows_written });
  }

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title="Historical data import"
        subtitle="CSV / Parquet / Excel / JSON → candles under provider import"
        actions={
          <span className="inline-flex h-5 items-center gap-1.5 rounded-full bg-raised px-2 text-[11px] font-medium uppercase tracking-wide text-text-2">
            <Database className="size-3" /> provider: import
          </span>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="text-[12px] text-text-3">
            Imported bars are stored as provider <code className="font-mono text-text-2">import</code> and carry that source everywhere they are shown. They are never
            presented as broker or exchange data. Run a dry run first; nothing is written until you commit.
          </p>

          {/* File drop / pick */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              void pickFile(e.dataTransfer.files[0] ?? null);
            }}
            className={cn(
              "flex min-h-20 cursor-pointer items-center justify-center gap-3 border border-dashed px-4 py-4 text-center transition-colors",
              dragging ? "border-accent bg-raised" : "border-border hover:border-border-strong hover:bg-raised",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => void pickFile(e.target.files?.[0] ?? null)}
            />
            <FileUp className="size-4 shrink-0 text-text-3" aria-hidden />
            {file ? (
              <div className="flex items-center gap-2 text-[13px]">
                <span className="font-medium text-text-1">{file.name}</span>
                <span className="tabular text-text-3">{formatNumber(file.size / 1024, 1)} KB</span>
                {columns.length > 0 && <span className="text-text-3">· {columns.length} columns</span>}
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Remove file"
                  onClick={(e) => {
                    e.stopPropagation();
                    void pickFile(null);
                    if (inputRef.current) inputRef.current.value = "";
                  }}
                >
                  <X />
                </Button>
              </div>
            ) : (
              <div className="text-[13px] text-text-2">
                Drop a file here or click to choose <span className="text-text-3">(csv, parquet, xlsx, json · up to 50 MB)</span>
              </div>
            )}
          </div>
          {fileError && <p className="text-xs text-down">{fileError}</p>}

          {/* Mapping */}
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <h3 className="text-[12px] font-semibold text-text-2">Column mapping</h3>
              {columns.length > 0 && <span className="text-[11px] text-text-3">Auto-filled from the CSV header; adjust as needed.</span>}
            </div>
            <ImportMappingForm mapping={mapping} columns={columns} disabled={upload.isPending} onChange={setMapping} />
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" disabled={!file || problems.length > 0 || upload.isPending} onClick={() => void runDry()}>
              <FlaskConical /> {upload.isPending && !confirming ? "Running…" : "Dry run"}
            </Button>
            {!confirming ? (
              <Button variant="primary" disabled={!canCommit} onClick={() => setConfirming(true)}>
                <Upload /> Commit import
              </Button>
            ) : (
              <div className="flex items-center gap-2 border border-warn/40 bg-warn/10 px-3 py-1 text-xs text-warn">
                <span>
                  Write {formatNumber(report?.rows_accepted ?? 0)} bars for {report?.coverage.length ?? 0} symbol(s) under provider <b>import</b>? Existing import bars for the same timestamps are overwritten.
                </span>
                <Button size="sm" variant="primary" disabled={upload.isPending} onClick={() => void runCommit()}>
                  {upload.isPending ? "Writing…" : "Yes, commit"}
                </Button>
                <Button size="sm" variant="ghost" disabled={upload.isPending} onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              </div>
            )}
            {problems.length > 0 && file && <span className="text-[11px] text-text-3">{problems[0]}</span>}
            {report && blocker && <span className="text-[11px] text-warn">{blocker}</span>}
            {report && !blocker && !isOwner && <span className="text-[11px] text-text-3">Only the owner can commit imports.</span>}
            {file && dryRun && !report && <span className="text-[11px] text-text-3">File or mapping changed since the last dry run; run it again.</span>}
          </div>
          {apiError && <p className="text-xs text-down">{apiError}</p>}
          {committed && (
            <p className="text-xs text-up">
              Import job #{committed.jobId} committed: {formatNumber(committed.rows)} bars written under provider import.
            </p>
          )}

          {/* Report */}
          {report && (
            <div className="flex flex-col gap-2 border-t border-border pt-3">
              <h3 className="text-[12px] font-semibold text-text-2">Dry-run report {committed ? "(committed)" : "(nothing written)"}</h3>
              <ImportReportView report={report} />
            </div>
          )}
        </div>
      </PanelCard>

      <PanelCard title="Import jobs" subtitle="Committed imports; the latest 50">
        <ImportJobsTable />
      </PanelCard>
    </div>
  );
}
