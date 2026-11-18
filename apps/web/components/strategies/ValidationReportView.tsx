import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import type { ValidationReport } from "@/lib/api/generated";

export function ValidationReportView({ report }: { report: ValidationReport | null | undefined }) {
  if (!report) return null;
  return (
    <div className="flex flex-col gap-1 text-[11px]">
      <p className={report.valid ? "flex items-center gap-1 text-up" : "flex items-center gap-1 text-down"}>
        {report.valid ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
        {report.valid ? "DSL valid" : `${report.errors.length} error(s)`}
      </p>
      {report.errors.map((e, i) => (
        <p key={`e${i}`} className="flex items-start gap-1 text-down"><XCircle className="mt-0.5 size-3 shrink-0" /> {e}</p>
      ))}
      {report.warnings.map((w, i) => (
        <p key={`w${i}`} className="flex items-start gap-1 text-warn"><AlertTriangle className="mt-0.5 size-3 shrink-0" /> {w}</p>
      ))}
      {report.missing_information.map((m, i) => (
        <p key={`m${i}`} className="flex items-start gap-1 text-text-2"><HelpCircle className="mt-0.5 size-3 shrink-0" /> missing: {m}</p>
      ))}
    </div>
  );
}
