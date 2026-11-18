"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, Wand2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AiBadge, PanelCard } from "@/components/design";
import { DslViewer } from "@/components/strategies/DslViewer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiRequestError } from "@/lib/api/client";
import type { NlDraft, NlGenerateRequest, NlLanguage } from "@/lib/api/generated";
import { useAnswerDraft, useGenerateStrategy, useSaveDraft } from "@/lib/api/nl";

const TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "1d", "1w"] as const;
const LANGUAGES: { v: NlLanguage; label: string }[] = [
  { v: "mr", label: "मराठी" },
  { v: "hi", label: "हिंदी" },
  { v: "en", label: "English" },
];
const EXAMPLE_MR =
  "EMA 9 ने EMA 21 ला वरच्या बाजूने cross केल्यावर आणि RSI 55 पेक्षा जास्त असल्यास Buy करा.";

function errorText(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof ApiRequestError) {
    if (err.status === 503) return "AI is not configured on this server (OPENAI_API_KEY is empty). Nothing was generated.";
    if (err.status === 429) return "The AI token budget for today is used up. Try again tomorrow or raise AI_DAILY_TOKEN_BUDGET.";
    if (err.status === 502) return "The AI service answered badly or not at all. Nothing was saved; try rephrasing.";
    if (err.status === 422) return "The API rejected the request. Check the fields and try again.";
    return err.message;
  }
  return "Cannot reach the API. Is the backend running?";
}

const selectClass =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm text-text-primary outline-none focus-visible:border-ring dark:bg-input/30";

export default function Page() {
  const router = useRouter();
  const [form, setForm] = useState<NlGenerateRequest>({
    language: "mr",
    market: "NSE",
    instrument: "NIFTY",
    timeframe: "5m",
    description: "",
  });
  const [draft, setDraft] = useState<NlDraft | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const generate = useGenerateStrategy();
  const answer = useAnswerDraft(draft?.draft_id ?? null);
  const save = useSaveDraft(draft?.draft_id ?? null);

  const onGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const d = await generate.mutateAsync(form);
      setDraft(d);
      setAnswers({});
    } catch {
      /* rendered below */
    }
  };

  const onAnswer = async () => {
    const items = Object.entries(answers)
      .filter(([, v]) => v.trim().length > 0)
      .map(([question_id, a]) => ({ question_id, answer: a.trim() }));
    if (!items.length) return;
    try {
      const d = await answer.mutateAsync({ answers: items });
      setDraft(d);
      setAnswers({});
    } catch {
      /* rendered below */
    }
  };

  const onSave = async () => {
    try {
      const v = await save.mutateAsync({ name: draft?.strategy_name ?? null });
      router.push(`/strategies/${v.strategy_id}`);
    } catch {
      /* rendered below */
    }
  };

  const err = errorText(generate.error ?? answer.error ?? save.error);
  const busy = generate.isPending || answer.isPending || save.isPending;

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title={<span className="flex items-center gap-2">Natural-language builder <AiBadge /></span>}
        subtitle="Describe the strategy in Marathi, Hindi or English. The AI drafts it; nothing you did not say is filled in."
        actions={<Link href="/strategies" className="text-[11px] text-accent-cyan">Back to library</Link>}
      >
        <form onSubmit={onGenerate} className="flex flex-col gap-3">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="lang">Language</Label>
              <select id="lang" className={selectClass} value={form.language ?? "en"} onChange={(e) => setForm({ ...form, language: e.target.value as NlLanguage })}>
                {LANGUAGES.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="market">Market</Label>
              <Input id="market" value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value.toUpperCase() })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="instrument">Instrument</Label>
              <Input id="instrument" value={form.instrument} onChange={(e) => setForm({ ...form, instrument: e.target.value.toUpperCase() })} placeholder="NIFTY, BANKNIFTY, RELIANCE…" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tf">Timeframe</Label>
              <select id="tf" className={selectClass} value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value as NlGenerateRequest["timeframe"] })}>
                {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="desc">Strategy description</Label>
            <textarea
              id="desc"
              required
              minLength={10}
              rows={4}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder={EXAMPLE_MR}
              className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm text-text-primary outline-none placeholder:text-muted-foreground focus-visible:border-ring dark:bg-input/30"
            />
            <button type="button" onClick={() => setForm({ ...form, description: EXAMPLE_MR })} className="self-start text-[11px] text-text-muted hover:text-text-secondary">
              Use the example from the master prompt
            </button>
          </div>
          {err && <p role="alert" className="text-xs text-pnl-negative">{err}</p>}
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={busy || form.description.trim().length < 10}>
              <Wand2 className="mr-1 size-3.5" /> {generate.isPending ? "Drafting…" : "Draft strategy"}
            </Button>
            <span className="text-[11px] text-text-muted">One AI call. Every call is logged in ai_calls with its token cost.</span>
          </div>
        </form>
      </PanelCard>

      {draft && (
        <div className="grid gap-3 lg:grid-cols-2">
          <PanelCard
            title={draft.strategy_name}
            subtitle={`${draft.market} · ${draft.instrument} · ${draft.timeframe} · ${draft.direction} · detected ${draft.detected_language} · draft ${draft.draft_id}`}
          >
            <div className="flex flex-col gap-3 text-xs">
              <Section title="Entry conditions" rows={draft.entry_conditions} empty="None extracted." />
              <Section title="Exit conditions" rows={draft.exit_conditions} empty="Not stated." />
              <div>
                <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Risk management</h4>
                <ul className="grid gap-1 md:grid-cols-3">
                  <Kv k="Stop loss" v={draft.risk_management.stop_loss} />
                  <Kv k="Target" v={draft.risk_management.target} />
                  <Kv k="Position sizing" v={draft.risk_management.position_sizing} />
                </ul>
              </div>
              {draft.unsupported.length > 0 && (
                <div>
                  <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-pnl-negative">Not in the indicator library</h4>
                  {draft.unsupported.map((u, i) => <p key={i} className="text-text-secondary">“{u}” — nothing was substituted for it.</p>)}
                </div>
              )}
              {draft.defaults_applied.length > 0 && (
                <div>
                  <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Defaults applied (not from your text)</h4>
                  {draft.defaults_applied.map((d, i) => <p key={i} className="flex items-start gap-1 text-text-secondary"><AlertTriangle className="mt-0.5 size-3 shrink-0 text-state-delayed" /> {d}</p>)}
                </div>
              )}
              {draft.changes.length > 0 && (
                <div>
                  <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Changed by your last answers</h4>
                  {draft.changes.map((c, i) => <p key={i} className="font-mono text-[11px] text-text-secondary">{c}</p>)}
                </div>
              )}
              <div>
                <p className={draft.validation.valid ? "flex items-center gap-1 text-pnl-positive" : "flex items-center gap-1 text-pnl-negative"}>
                  {draft.validation.valid ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
                  {draft.validation.valid ? "DSL valid as a draft" : `${draft.validation.errors.length} error(s)`}
                </p>
                {draft.validation.errors.map((e, i) => <p key={`e${i}`} className="flex items-start gap-1 text-pnl-negative"><XCircle className="mt-0.5 size-3 shrink-0" /> {e}</p>)}
                {draft.validation.warnings.map((w, i) => <p key={`w${i}`} className="flex items-start gap-1 text-state-delayed"><AlertTriangle className="mt-0.5 size-3 shrink-0" /> {w}</p>)}
                {draft.missing_information.map((m, i) => <p key={`m${i}`} className="flex items-start gap-1 text-text-secondary"><HelpCircle className="mt-0.5 size-3 shrink-0" /> missing: {m}</p>)}
              </div>
            </div>
          </PanelCard>

          <div className="flex flex-col gap-3">
            <PanelCard title="Clarification questions" subtitle={draft.clarification_questions.length ? "Answer what you can; the draft updates only those fields." : "Nothing left to ask."}>
              {draft.status !== "draft" ? (
                <p className="text-xs text-text-muted">This draft was saved as a strategy version{draft.strategy_version_id ? ` (#${draft.strategy_version_id})` : ""}.</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {draft.clarification_questions.map((q) => (
                    <div key={q.id} className="flex flex-col gap-1">
                      <Label htmlFor={q.id} className="text-xs leading-snug">
                        <span className="mr-1 font-mono text-[10px] text-text-muted">{q.id} · {q.field}</span>
                        <span className="block text-text-primary">{q.question_local}</span>
                        {q.question_local !== q.question_en && <span className="block text-[11px] text-text-muted">{q.question_en}</span>}
                      </Label>
                      <Input id={q.id} value={answers[q.id] ?? ""} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} placeholder="Your answer, in any of the three languages" />
                    </div>
                  ))}
                  <div className="flex flex-wrap items-center gap-2">
                    {draft.clarification_questions.length > 0 && (
                      <Button type="button" variant="outline" disabled={busy || !Object.values(answers).some((v) => v.trim())} onClick={onAnswer}>
                        {answer.isPending ? "Updating…" : "Send answers"}
                      </Button>
                    )}
                    <Button type="button" disabled={busy || !draft.validation.valid} onClick={onSave} title={draft.validation.valid ? "Creates a strategy with this DSL as its first draft version" : "Fix the errors first"}>
                      Save as draft strategy <ArrowRight className="ml-1 size-3.5" />
                    </Button>
                    <span className="text-[11px] text-text-muted">Saving never activates anything; the version starts in draft.</span>
                  </div>
                </div>
              )}
            </PanelCard>
            <PanelCard title="Strategy DSL" subtitle={`original text pinned · ${draft.ai_call_ids.length} AI call(s): ${draft.ai_call_ids.join(", ") || "—"}`}>
              <DslViewer dsl={draft.dsl} />
            </PanelCard>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ title, rows, empty }: { title: string; rows: { original_phrase: string; rule: string }[]; empty: string }) {
  return (
    <div>
      <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-text-muted">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {rows.map((r, i) => (
            <li key={i} className="rounded-sm border border-border-subtle/60 px-2 py-1">
              <p className="font-mono text-[11px] text-text-primary">{r.rule}</p>
              <p className="text-[11px] text-text-muted">“{r.original_phrase}”</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string | null }) {
  return (
    <li className="rounded-sm border border-border-subtle/60 px-2 py-1">
      <p className="text-[10px] uppercase tracking-wide text-text-muted">{k}</p>
      <p className={v ? "text-text-primary" : "text-text-muted"}>{v ?? "not stated"}</p>
    </li>
  );
}
