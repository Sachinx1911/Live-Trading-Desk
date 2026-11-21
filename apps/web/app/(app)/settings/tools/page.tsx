"use client";

import { useState } from "react";
import { Check, Copy, TriangleAlert } from "lucide-react";
import { EmptyState, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { ToolCallStatus, ToolLevel, ToolTokenCreated } from "@/lib/api/generated";
import { useCreateToolToken, useRevokeToolToken, useToolCalls, useToolTokens } from "@/lib/api/tool-server";
import { cn } from "@/lib/utils";

const TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function when(iso: string | null): string {
  return iso ? `${TIME.format(new Date(iso))} IST` : "—";
}

const STATUS_TONE: Record<ToolCallStatus, string> = {
  ok: "text-up",
  error: "text-warn",
  refused: "text-down",
};

function NewToken({ created, onDone }: { created: ToolTokenCreated; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div role="alert" className="flex flex-col gap-2 border border-warn/40 bg-warn-soft p-3 text-xs">
      <div className="flex items-center gap-2 font-medium text-warn">
        <TriangleAlert className="size-4" aria-hidden />
        Copy this token now. It is shown once and cannot be shown again.
      </div>
      <p className="text-text-2">
        Store it in jarvis&apos;s Keychain (connector <code className="font-mono">trading</code>). Anyone
        holding it can call the {created.max_level} tools of the tool server; revoke it below if it leaks.
      </p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate border border-border bg-app px-2 py-1.5 font-mono text-[12px] text-text-1">
          {created.token}
        </code>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            void navigator.clipboard.writeText(created.token).then(() => setCopied(true));
          }}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button size="sm" onClick={onDone}>
          Done
        </Button>
      </div>
    </div>
  );
}

function Tokens() {
  const tokens = useToolTokens();
  const create = useCreateToolToken();
  const revoke = useRevokeToolToken();
  const [name, setName] = useState("jarvis");
  const [level, setLevel] = useState<ToolLevel>("green");
  const [created, setCreated] = useState<ToolTokenCreated | null>(null);

  return (
    <PanelCard
      title="Service tokens"
      subtitle="One per jarvis install. Only a SHA-256 hash is stored."
      bodyClassName="flex flex-col gap-3 text-xs"
    >
      {created ? (
        <NewToken created={created} onDone={() => setCreated(null)} />
      ) : (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({ name, max_level: level }, { onSuccess: (t) => setCreated(t) });
          }}
        >
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-text-3">
            Name
            <Input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1 text-text-3">
            Max level
            <select
              className="h-9 rounded-[var(--r-md)] border border-border bg-app px-2 text-[14px] text-text-1"
              value={level}
              onChange={(e) => setLevel(e.target.value as ToolLevel)}
            >
              <option value="green">green (read only)</option>
              <option value="yellow">yellow (from Stage 5)</option>
            </select>
          </label>
          <Button type="submit" variant="primary" disabled={create.isPending || !name.trim()}>
            Create token
          </Button>
          {create.isError && <span className="text-down">{(create.error as Error).message}</span>}
        </form>
      )}
      <p className="text-text-3">
        The server serves the lower of its own ceiling (<code className="font-mono">TOOL_SERVER_MAX_LEVEL</code>,
        green in Stage 4) and the token&apos;s max level. Red actions are never served.
      </p>
      {tokens.isPending && <Skeleton className="h-16" />}
      {tokens.isError && <EmptyState title="Cannot load tokens" description="Owner only; is the API up?" />}
      {tokens.data && tokens.data.length === 0 && (
        <p className="text-text-3">No tokens yet.</p>
      )}
      {tokens.data && tokens.data.length > 0 && (
        <table className="w-full">
          <thead className="text-[11px] uppercase tracking-wide text-text-3">
            <tr className="border-b border-border">
              <th className="py-1.5 text-left font-medium">Name</th>
              <th className="py-1.5 text-left font-medium">Prefix</th>
              <th className="py-1.5 text-left font-medium">Level</th>
              <th className="py-1.5 text-left font-medium">Created</th>
              <th className="py-1.5 text-left font-medium">Last used</th>
              <th className="py-1.5 text-right font-medium">State</th>
            </tr>
          </thead>
          <tbody>
            {tokens.data.map((t) => (
              <tr key={t.id} className="border-b border-border last:border-0">
                <td className="py-1.5 text-text-1">{t.name}</td>
                <td className="py-1.5 font-mono text-text-2">{t.prefix}…</td>
                <td className="py-1.5 font-mono uppercase text-text-2">{t.max_level}</td>
                <td className="py-1.5 text-text-2">{when(t.created_at)}</td>
                <td className="py-1.5 text-text-2">{when(t.last_used_at)}</td>
                <td className="py-1.5 text-right">
                  {t.revoked_at ? (
                    <span className="text-text-3">revoked {when(t.revoked_at)}</span>
                  ) : (
                    <Button
                      size="xs"
                      variant="destructive"
                      disabled={revoke.isPending}
                      onClick={() => {
                        if (window.confirm(`Revoke "${t.name}"? Calls with it are refused at once.`)) {
                          revoke.mutate(t.id);
                        }
                      }}
                    >
                      Revoke
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </PanelCard>
  );
}

const FILTERS: (ToolCallStatus | "")[] = ["", "ok", "error", "refused"];

function Calls() {
  const [status, setStatus] = useState<ToolCallStatus | "">("");
  const calls = useToolCalls(status, 100);
  return (
    <PanelCard
      title="Recent tool calls"
      subtitle="Authority log: every call, allowed or refused"
      actions={
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <Button key={f || "all"} size="xs" variant={status === f ? "default" : "ghost"} onClick={() => setStatus(f)}>
              {f || "all"}
            </Button>
          ))}
        </div>
      }
      bodyClassName="p-0 text-xs"
    >
      {calls.isPending && <Skeleton className="m-3 h-24" />}
      {calls.isError && <EmptyState title="Cannot load the call log" description="Owner only; is the API up?" />}
      {calls.data && calls.data.length === 0 && <p className="p-3 text-text-3">No calls yet.</p>}
      {calls.data && calls.data.length > 0 && (
        <table className="w-full">
          <thead className="text-[11px] uppercase tracking-wide text-text-3">
            <tr className="border-b border-border">
              <th className="px-3 py-1.5 text-left font-medium">Time</th>
              <th className="px-3 py-1.5 text-left font-medium">Token</th>
              <th className="px-3 py-1.5 text-left font-medium">Via</th>
              <th className="px-3 py-1.5 text-left font-medium">Tool</th>
              <th className="px-3 py-1.5 text-left font-medium">Status</th>
              <th className="px-3 py-1.5 text-left font-medium">Data</th>
              <th className="px-3 py-1.5 text-right font-medium">ms</th>
            </tr>
          </thead>
          <tbody>
            {calls.data.map((c) => (
              <tr key={c.id} className="border-b border-border last:border-0 align-top">
                <td className="whitespace-nowrap px-3 py-1.5 text-text-2">{when(c.ts)}</td>
                <td className="px-3 py-1.5 text-text-2">{c.token_name ?? "—"}</td>
                <td className="px-3 py-1.5 font-mono uppercase text-text-3">{c.transport}</td>
                <td className="px-3 py-1.5 font-mono text-text-1">
                  {c.tool}
                  {c.level && <span className="ml-1 text-[10px] uppercase text-text-3">{c.level}</span>}
                </td>
                <td className={cn("px-3 py-1.5 font-mono uppercase", STATUS_TONE[c.status])}>
                  {c.status}
                  {c.error && <div className="normal-case text-text-3">{c.error}</div>}
                </td>
                <td className="px-3 py-1.5 text-text-2">
                  {c.result_meta.freshness ? (
                    <span>
                      {c.result_meta.freshness}
                      {c.result_meta.is_demo ? " · DEMO" : ""}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-1.5 text-right font-mono text-text-3">{c.duration_ms ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </PanelCard>
  );
}

export default function Page() {
  return (
    <div className="flex flex-col gap-3">
      <PanelCard title="Tool server for jarvis" bodyClassName="text-xs text-text-2">
        <p>
          The tool server (<code className="font-mono text-text-1">make tool-server</code>, 127.0.0.1:8100)
          lets the owner&apos;s jarvis read trading data over typed HTTP (<code className="font-mono">/tools</code>)
          or MCP (<code className="font-mono">/mcp</code>). Stage 4 serves green, read-only tools; every answer
          carries its source, freshness and a demo flag. No tool places, changes or cancels an order. See{" "}
          <code className="font-mono">docs/tool-server.md</code>.
        </p>
      </PanelCard>
      <Tokens />
      <Calls />
    </div>
  );
}
