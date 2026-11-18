"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError, api } from "@/lib/api/client";
import { useDslCatalogue } from "@/lib/api/dsl";
import type { StrategyVersion, ValidationReport, VersionIn } from "@/lib/api/generated";
import { useCreateStrategy, useEditVersion, useStrategyVersion, useValidateDsl } from "@/lib/api/trading";
import { DSL_EXAMPLES } from "@/lib/dsl/examples";
import { cleanDoc, clientValidate, coerceDoc, emptyDoc, type DslDoc } from "@/lib/dsl/types";
import { BasicsSection } from "./BasicsSection";
import { IndicatorsSection } from "./IndicatorsSection";
import { RightRail } from "./RightRail";
import { RiskSection } from "./RiskSection";
import { RulesSection } from "./RulesSection";
import { SessionSection } from "./SessionSection";

const DRAFT_PREFIX = "tp.visual-builder.draft:";
const draftKey = (from: string | null) => `${DRAFT_PREFIX}${from ?? "new"}`;

type Draft = { doc: DslDoc; savedAt: string };

function readDraft(from: string | null): Draft | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(draftKey(from));
    if (!raw) return null;
    const d = JSON.parse(raw) as Draft;
    if (!d?.doc || typeof d.doc !== "object") return null;
    return { doc: coerceDoc(d.doc as unknown as Record<string, unknown>), savedAt: d.savedAt };
  } catch {
    return null;
  }
}

/** Loads the source version (when `?from=`) and mounts the form once the initial document is known. */
export function VisualBuilder({ from }: { from: string | null }) {
  const fromId = from && /^\d+$/.test(from) ? Number(from) : null;
  const version = useStrategyVersion(fromId);
  if (fromId != null && version.isError) return <p className="text-[12px] text-down">Could not load version {from}.</p>;
  if (fromId != null && !version.data) return <Skeleton className="h-64 w-full" />;
  return <BuilderForm key={from ?? "new"} from={from} fromId={fromId} source={version.data ?? null} />;
}

function BuilderForm({ from, fromId, source }: { from: string | null; fromId: number | null; source: StrategyVersion | null }) {
  const router = useRouter();
  const { catalogue, fromServer } = useDslCatalogue();
  const validate = useValidateDsl();
  const createStrategy = useCreateStrategy();
  const editVersion = useEditVersion();

  // Draft (if any) beats the version/empty document, so a reload never loses work.
  const [initial] = useState(() => {
    const draft = readDraft(from);
    if (draft) return { doc: draft.doc, info: `Restored unsaved draft from ${new Date(draft.savedAt).toLocaleString()}` };
    return { doc: source ? coerceDoc(source.dsl) : emptyDoc(), info: null };
  });
  const [doc, setDoc] = useState<DslDoc>(initial.doc);
  const [draftInfo, setDraftInfo] = useState<string | null>(initial.info);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Autosave (debounced) to localStorage keyed by `from`.
  useEffect(() => {
    const t = setTimeout(() => {
      try {
        window.localStorage.setItem(draftKey(from), JSON.stringify({ doc, savedAt: new Date().toISOString() } satisfies Draft));
      } catch { /* quota or private mode */ }
    }, 400);
    return () => clearTimeout(t);
  }, [doc, from]);

  const onChange = useCallback((p: Partial<DslDoc>) => {
    setDoc((d) => ({ ...d, ...p }));
    setReport(null);
  }, []);

  const json = useMemo(() => cleanDoc(doc), [doc]);
  const clientErrors = useMemo(() => clientValidate(doc), [doc]);

  const discardDraft = () => {
    window.localStorage.removeItem(draftKey(from));
    setDraftInfo(null);
    setDoc(source ? coerceDoc(source.dsl) : emptyDoc());
    setReport(null);
  };

  const save = async (summary: string) => {
    setSaveError(null);
    setSavingVersion(true);
    const dsl = cleanDoc({ ...doc, origin: doc.origin === "user_visual" || doc.origin === "import" ? doc.origin : "user_visual" });
    try {
      let strategyId: number;
      if (fromId != null && source) {
        const v = await editVersion.mutateAsync({ versionId: fromId, dsl, change_summary: summary || "Edited in visual builder" });
        strategyId = v.strategy_id;
      } else {
        const s = await createStrategy.mutateAsync({ name: doc.name.trim(), origin: "user_visual", description: doc.description ?? null });
        // The version hook is bound to a strategy id at render time; the id only exists now, so call the endpoint directly.
        await api<StrategyVersion>(`/strategies/${s.id}/versions`, { method: "POST", body: JSON.stringify({ dsl, change_summary: summary || "Created in visual builder" } satisfies VersionIn) });
        strategyId = s.id;
      }
      window.localStorage.removeItem(draftKey(from));
      router.push(`/strategies/${strategyId}`);
    } catch (e) {
      setSaveError(e instanceof ApiRequestError ? e.message : "Save failed");
    } finally {
      setSavingVersion(false);
    }
  };

  const [savingVersion, setSavingVersion] = useState(false);
  const saving = createStrategy.isPending || editVersion.isPending || savingVersion;
  const title = source ? `Editing version ${source.version_no} → new version` : "New strategy";

  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-12 flex flex-col gap-3 xl:col-span-8">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-medium text-text-1">{title}</h2>
          <span className="text-[10px] text-text-3">Autosaves locally · nothing is sent until you save</span>
        </div>
        <BasicsSection doc={doc} onChange={onChange} catalogue={catalogue} />
        <SessionSection doc={doc} onChange={onChange} catalogue={catalogue} />
        <IndicatorsSection doc={doc} onChange={onChange} catalogue={catalogue} />
        <RulesSection doc={doc} onChange={onChange} catalogue={catalogue} />
        <RiskSection doc={doc} onChange={onChange} catalogue={catalogue} />
      </div>
      <div className="col-span-12 xl:col-span-4">
        <RightRail
          json={json}
          clientErrors={clientErrors}
          report={report}
          validating={validate.isPending}
          onValidate={async () => {
            try { setReport(await validate.mutateAsync(json)); } catch (e) { setSaveError(e instanceof ApiRequestError ? e.message : "Validation request failed"); }
          }}
          onLoadExample={(key) => {
            const ex = DSL_EXAMPLES[key];
            if (ex) { setDoc(coerceDoc({ ...ex.doc, origin: "user_visual" })); setReport(null); }
          }}
          onSave={save}
          saving={saving}
          saveLabel={fromId != null ? "Save as new version" : "Save as new strategy"}
          saveError={saveError}
          draftInfo={draftInfo}
          onDiscardDraft={discardDraft}
          catalogueSource={fromServer ? "server" : "fallback"}
        />
      </div>
    </div>
  );
}
