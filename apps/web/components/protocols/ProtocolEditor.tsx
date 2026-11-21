"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RiskBadge } from "@/components/protocols/RiskBadge";
import { ApiRequestError } from "@/lib/api/client";
import type { Protocol, ProtocolAction, ProtocolStepIn } from "@/lib/api/generated";
import { useDeleteProtocol, useSaveProtocol } from "@/lib/api/protocols";

const EXAMPLE = JSON.stringify(
  [
    { tool: "health_check", args: {}, on_error: "continue" },
    { tool: "pcr_now", args: { symbols: ["NIFTY"] }, on_error: "continue" },
  ],
  null,
  2,
);

type Check = { steps: ProtocolStepIn[] | null; errors: string[] };

/** Client-side pre-check against /protocols/actions; the API validates again on save. */
function check(text: string, actions: ProtocolAction[], confirm: boolean): Check {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    return { steps: null, errors: [`JSON: ${(e as Error).message}`] };
  }
  if (!Array.isArray(raw) || raw.length === 0) return { steps: null, errors: ["steps must be a non-empty JSON array"] };
  const byName = new Map(actions.map((a) => [a.name, a]));
  const errors: string[] = [];
  raw.forEach((s, i) => {
    if (typeof s !== "object" || s === null || typeof (s as { tool?: unknown }).tool !== "string") {
      errors.push(`step ${i + 1}: needs a "tool" string`);
      return;
    }
    const st = s as ProtocolStepIn & Record<string, unknown>;
    const extra = Object.keys(st).filter((k) => !["tool", "args", "on_error"].includes(k));
    if (extra.length) errors.push(`step ${i + 1}: unknown field(s) ${extra.join(", ")}`);
    const a = byName.get(st.tool);
    if (!a) errors.push(`step ${i + 1}: unknown action "${st.tool}"`);
    else if (a.risk === "red" && !confirm) errors.push(`step ${i + 1} (${st.tool}): red action needs "ask before running"`);
    if (st.on_error !== undefined && st.on_error !== "stop" && st.on_error !== "continue")
      errors.push(`step ${i + 1}: on_error must be "stop" or "continue"`);
  });
  return { steps: raw as ProtocolStepIn[], errors };
}

export function ProtocolEditor({ protocols, actions }: { protocols: Protocol[]; actions: ProtocolAction[] }) {
  const owned = protocols.filter((p) => p.editable);
  const [selected, setSelected] = useState<string>("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [text, setText] = useState(EXAMPLE);
  const save = useSaveProtocol();
  const del = useDeleteProtocol();
  const isNew = selected === "";

  const load = (c: string) => {
    setSelected(c);
    const p = owned.find((x) => x.code === c);
    save.reset();
    if (!p) {
      setCode("");
      setName("");
      setDescription("");
      setConfirm(false);
      setText(EXAMPLE);
      return;
    }
    setCode(p.code);
    setName(p.name);
    setDescription(p.description ?? "");
    setConfirm(p.confirm_required);
    setText(JSON.stringify(p.steps.map(({ tool, args, on_error }) => ({ tool, args, on_error })), null, 2));
  };

  const res = useMemo(() => check(text, actions, confirm), [text, actions, confirm]);
  const risks = (res.steps ?? []).map((s) => actions.find((a) => a.name === s.tool)?.risk ?? "unknown");
  const err = save.error instanceof ApiRequestError ? save.error.message : save.error ? "Cannot reach the API." : null;

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_18rem]">
      <form
        className="flex flex-col gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!res.steps || res.errors.length) return;
          const p = await save.mutateAsync({
            code,
            isNew,
            body: { name, description: description || null, steps: res.steps, confirm_required: confirm },
          });
          setSelected(p.code);
        }}
      >
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <label className="text-text-2" htmlFor="pe-select">Protocol</label>
          <select id="pe-select" value={selected} onChange={(e) => load(e.target.value)} className="h-7 border border-border bg-raised px-2 text-[12px]">
            <option value="">New protocol…</option>
            {owned.map((p) => (
              <option key={p.code} value={p.code}>
                {p.name} ({p.code}, v{p.version})
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input required disabled={!isNew} value={code} onChange={(e) => setCode(e.target.value)} placeholder="code (lower_case)" pattern="[a-z][a-z0-9_]{1,47}" className="h-8 font-mono text-xs" />
          <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="h-8 text-xs" />
        </div>
        <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" className="h-8 text-xs" />
        <label className="flex items-center gap-2 text-[12px] text-text-2">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> Ask before running (required for red actions)
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          rows={12}
          aria-label="Steps JSON"
          className="rounded-[var(--r-sm)] border border-border bg-raised p-2 font-mono text-[12px] text-text-1"
        />
        <div className="flex flex-wrap items-center gap-1">
          {risks.map((r, i) => (
            <span key={i} className="flex items-center gap-1 text-[11px] text-text-3">
              {i + 1}.<RiskBadge risk={r} />
            </span>
          ))}
        </div>
        {res.errors.length > 0 && (
          <ul className="text-[12px] text-down">
            {res.errors.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
        {err && <p className="text-[12px] text-down">{err}</p>}
        {save.isSuccess && <p className="text-[12px] text-up">Saved as version {save.data.version}.</p>}
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" disabled={save.isPending || res.errors.length > 0}>
            {isNew ? "Create" : "Save new version"}
          </Button>
          {!isNew && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={del.isPending}
              onClick={async () => {
                if (!window.confirm(`Delete protocol ${selected}? Its run history is deleted with it.`)) return;
                await del.mutateAsync(selected);
                load("");
              }}
            >
              Delete
            </Button>
          )}
        </div>
      </form>
      <div className="flex flex-col gap-1">
        <p className="hud-label text-[11px] text-text-3">Available actions</p>
        <ul className="flex flex-col gap-1.5">
          {actions.map((a) => (
            <li key={a.name} className="text-[12px]">
              <div className="flex items-center gap-2">
                <span className="font-mono text-text-1">{a.name}</span>
                <RiskBadge risk={a.risk} />
              </div>
              <p className="text-[11px] text-text-3">{a.description}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
