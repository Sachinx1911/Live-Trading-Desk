"use client";

import { Check, Copy, FileJson, Save } from "lucide-react";
import { useState } from "react";
import { DslViewer } from "@/components/strategies/DslViewer";
import { ValidationReportView } from "@/components/strategies/ValidationReportView";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ValidationReport } from "@/lib/api/generated";
import { DSL_EXAMPLES } from "@/lib/dsl/examples";
import { Select } from "./fields";

export function RightRail({ json, clientErrors, report, validating, onValidate, onLoadExample, onSave, saving, saveLabel, saveError, draftInfo, onDiscardDraft, catalogueSource }: {
  json: Record<string, unknown>;
  clientErrors: string[];
  report: ValidationReport | null;
  validating: boolean;
  onValidate: () => void;
  onLoadExample: (key: string) => void;
  onSave: (summary: string) => void;
  saving: boolean;
  saveLabel: string;
  saveError: string | null;
  draftInfo: string | null;
  onDiscardDraft: () => void;
  catalogueSource: "server" | "fallback";
}) {
  const [example, setExample] = useState(Object.keys(DSL_EXAMPLES)[0]);
  const [summary, setSummary] = useState("");
  const [view, setView] = useState<"tree" | "raw">("tree");
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(json, null, 2);

  return (
    <aside className="flex flex-col gap-3 xl:sticky xl:top-2">
      <section className="border border-border bg-pane">
        <header className="flex h-9 items-center justify-between border-b border-border px-3">
          <h3 className="text-[12px] font-medium text-text-1">Save</h3>
          <span className="text-[10px] text-text-3">catalogue: {catalogueSource}</span>
        </header>
        <div className="flex flex-col gap-2 p-3">
          <div className="flex gap-1">
            <Select value={example} options={Object.keys(DSL_EXAMPLES)} labels={Object.fromEntries(Object.entries(DSL_EXAMPLES).map(([k, v]) => [k, v.label]))} className="flex-1" onChange={setExample} />
            <Button size="xs" variant="outline" onClick={() => onLoadExample(example)}><FileJson /> Load example</Button>
          </div>
          <Button size="sm" variant="outline" disabled={validating} onClick={onValidate}><Check /> Validate on server</Button>
          {clientErrors.length > 0 && (
            <ul className="flex flex-col gap-0.5 text-[11px] text-down">
              {clientErrors.map((e) => <li key={e}>• {e}</li>)}
            </ul>
          )}
          {clientErrors.length === 0 && <span className="text-[11px] text-up">Form checks pass.</span>}
          <ValidationReportView report={report} />
          <Input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Change summary (what and why)" className="h-8 text-xs" />
          <Button size="sm" disabled={saving || clientErrors.length > 0} onClick={() => onSave(summary.trim())}><Save /> {saveLabel}</Button>
          {saveError && <span className="text-[11px] text-down">{saveError}</span>}
          {draftInfo && (
            <div className="flex items-center justify-between text-[10px] text-text-3">
              <span>{draftInfo}</span>
              <Button size="xs" variant="ghost" onClick={onDiscardDraft}>Discard draft</Button>
            </div>
          )}
        </div>
      </section>

      <section className="border border-border bg-pane">
        <header className="flex h-9 items-center justify-between border-b border-border px-3">
          <h3 className="text-[12px] font-medium text-text-1">DSL JSON</h3>
          <div className="flex items-center gap-1">
            <Button size="xs" variant={view === "tree" ? "secondary" : "ghost"} onClick={() => setView("tree")}>Tree</Button>
            <Button size="xs" variant={view === "raw" ? "secondary" : "ghost"} onClick={() => setView("raw")}>Raw</Button>
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label="Copy JSON"
              onClick={async () => {
                try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* clipboard unavailable */ }
              }}
            >
              {copied ? <Check /> : <Copy />}
            </Button>
          </div>
        </header>
        <div className="max-h-[70vh] overflow-auto">
          {view === "tree" ? (
            <DslViewer dsl={json} className="border-0" />
          ) : (
            <pre className="p-2 font-mono text-[10px] leading-snug text-text-2">{text}</pre>
          )}
        </div>
      </section>
    </aside>
  );
}
