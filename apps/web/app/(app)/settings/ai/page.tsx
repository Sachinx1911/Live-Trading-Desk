"use client";

import { Bot, KeyRound, ShieldOff } from "lucide-react";
import { AiBadge, PanelCard } from "@/components/design";
import { Skeleton } from "@/components/ui/skeleton";
import type { HealthResponse } from "@/lib/api/generated";
import { useHealth } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

/** Fields the API's /health returns that the generated client type does not list yet. */
type HealthWithLlm = HealthResponse & { llm?: string; env?: string; provider?: string };

const PHASE6: { title: string; what: string }[] = [
  { title: "Natural-language builder (evaluated)", what: "Plain-English rules → DSL draft, scored against the deterministic parser before it is shown." },
  { title: "Candidate generation, Mode A", what: "Research jobs propose draft strategy versions with linked backtest evidence; nothing is activated by the model." },
  { title: "Trade review", what: "Post-session review of paper/live trades against the strategy's own rules, written as a report." },
  { title: "Daily report", what: "Morning brief and end-of-day summary from stored data; every number cites its source row." },
];

export default function Page() {
  const health = useHealth();
  const data = health.data as HealthWithLlm | undefined;
  const llm = data?.llm ?? null;
  const configured = !!llm && llm !== "not_configured";
  const [provider, model] = configured && llm ? llm.split(":", 2) : [null, null];

  return (
    <div className="flex flex-col gap-3">
      <PanelCard
        title="AI"
        subtitle="Phase 6 — nothing here acts yet"
        actions={
          health.isPending ? (
            <Skeleton className="h-5 w-28" />
          ) : (
            <span
              className={cn(
                "inline-flex h-5 items-center gap-1.5 rounded-full bg-raised px-2 text-[11px] font-medium uppercase tracking-wide",
                configured ? "text-ai" : "text-text-3",
              )}
              aria-label={`LLM status: ${configured ? llm : "not configured"}`}
            >
              <span className={cn("size-1.5 rounded-full", configured ? "bg-ai" : "bg-text-3")} />
              {configured ? <span className="normal-case tracking-normal">{llm}</span> : "Not configured"}
            </span>
          )
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
            <dt className="text-text-3">Status</dt>
            <dd className="text-text-1">{health.isPending ? "…" : health.error ? "API unreachable" : configured ? "Configured" : "Not configured"}</dd>
            <dt className="text-text-3">Provider</dt>
            <dd className="font-mono text-text-1">{provider ?? "—"}</dd>
            <dt className="text-text-3">Model</dt>
            <dd className="font-mono text-text-1">{model ?? "—"}</dd>
            <dt className="text-text-3">Base URL</dt>
            <dd className="text-text-3">Not exposed by /health; set with OPENAI_BASE_URL on the server.</dd>
            <dt className="text-text-3">Environment</dt>
            <dd className="font-mono text-text-1">{data?.env ?? "—"}</dd>
          </dl>
          <div className="flex flex-col gap-2 border border-border bg-raised p-3 text-[12px] text-text-2">
            <div className="flex items-center gap-2 text-text-1">
              <KeyRound className="size-3.5 text-accent" /> <span className="font-medium">Where the key lives</span>
            </div>
            <p>
              The API key is read only from the server&apos;s <code className="font-mono">.env</code> as <code className="font-mono">OPENAI_API_KEY</code> (with{" "}
              <code className="font-mono">LLM_PROVIDER</code>, <code className="font-mono">OPENAI_MODEL</code>, <code className="font-mono">OPENAI_BASE_URL</code>). This page never
              collects or displays a secret; there is no input for it by design. Change the file and restart the API, then this status updates.
            </p>
          </div>
        </div>
      </PanelCard>

      <PanelCard title="What the model may and may not do" subtitle="ADR-009" actions={<AiBadge />}>
        <div className="flex gap-3 text-[13px] text-text-2">
          <ShieldOff className="mt-0.5 size-4 shrink-0 text-text-3" aria-hidden />
          <p>
            Every LLM call goes through one provider interface with a JSON schema and Pydantic validation. The model may write strategy DSL <em>drafts</em>,
            clarification questions, trade reviews, research reports and candidate versions in <em>draft</em> status. It cannot place, modify or cancel an
            order, change risk limits, activate a strategy or touch the kill switch — those capabilities do not exist on the AI side, so there is nothing to
            misuse. Every call is logged in <code className="font-mono">ai_calls</code> with model, prompt version, tokens, cost and the ids of the data it saw,
            and each job runs under a mandatory token budget.
          </p>
        </div>
      </PanelCard>

      <PanelCard title="Coming in Phase 6" subtitle="Not simulated here; each item lands when it is implemented, tested and documented">
        <ul className="grid gap-2 md:grid-cols-2">
          {PHASE6.map((f) => (
            <li key={f.title} className="flex gap-3 border border-border p-3">
              <Bot className="mt-0.5 size-4 shrink-0 text-text-3" aria-hidden />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-medium text-text-1">{f.title}</span>
                  <span className="rounded-sm border border-border px-1 text-[10px] text-text-3">P6</span>
                </div>
                <p className="text-[12px] text-text-3">{f.what}</p>
              </div>
            </li>
          ))}
        </ul>
      </PanelCard>
    </div>
  );
}
