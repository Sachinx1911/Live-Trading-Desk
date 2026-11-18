"use client";

import { Check, Save } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/lib/api/client";
import type { ValidationReport } from "@/lib/api/generated";
import { useValidateDsl } from "@/lib/api/trading";
import { ValidationReportView } from "./ValidationReportView";

export const EXAMPLE_NAMES = ["ema_rsi_nifty", "banknifty_vwap_reversion", "nifty50_daily_breakout"];

/** Plain JSON editor for a DSL document (Phase 3). Visual and natural-language builders arrive in Phase 5. */
export function DslEditor({
  initial,
  onSave,
  saving,
  saveLabel = "Save as new draft version",
}: {
  initial: Record<string, unknown>;
  onSave: (dsl: Record<string, unknown>, changeSummary: string) => Promise<void>;
  saving?: boolean;
  saveLabel?: string;
}) {
  const [text, setText] = useState(JSON.stringify(initial, null, 2));
  const [summary, setSummary] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const validate = useValidateDsl();

  const parse = (): Record<string, unknown> | null => {
    try {
      const v = JSON.parse(text) as unknown;
      if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("document must be a JSON object");
      setParseError(null);
      return v as Record<string, unknown>;
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "invalid JSON");
      return null;
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        className="min-h-96 w-full rounded-sm border border-border-subtle bg-panel-raised p-2 font-mono text-[11px] leading-snug text-text-primary"
        aria-label="Strategy DSL JSON"
      />
      {parseError && <p className="text-[11px] text-pnl-negative">JSON: {parseError}</p>}
      <ValidationReportView report={report} />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={validate.isPending}
          onClick={async () => {
            const d = parse();
            if (d) setReport(await validate.mutateAsync(d));
          }}
        >
          <Check /> Validate
        </Button>
        <Input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Change summary (what and why)" className="h-8 w-72 text-xs" />
        <Button
          type="button"
          size="sm"
          disabled={saving}
          onClick={async () => {
            const d = parse();
            if (!d) return;
            setSaveError(null);
            try {
              await onSave(d, summary.trim());
            } catch (e) {
              setSaveError(e instanceof ApiRequestError ? e.message : "Save failed");
            }
          }}
        >
          <Save /> {saveLabel}
        </Button>
        {saveError && <span className="text-[11px] text-pnl-negative">{saveError}</span>}
      </div>
      <p className="text-[11px] text-text-muted">
        Examples available server-side as `strategy.dsl.examples`: {EXAMPLE_NAMES.join(", ")}. Paste a document here; the natural-language and visual builders ship in Phase 5.
      </p>
    </div>
  );
}
