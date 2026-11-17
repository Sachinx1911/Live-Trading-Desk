"use client";

import { Check, Copy, ExternalLink, KeyRound, LogIn, LogOut } from "lucide-react";
import { useState } from "react";
import { DataStateBadge, PanelCard } from "@/components/design";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { API_URL, ApiRequestError } from "@/lib/api/client";
import type { BrokerCode, BrokerSessionStatus } from "@/lib/api/generated";
import { useBrokerLoginUrl, useBrokerLogout, useUpsertBrokerAccount } from "@/lib/api/queries";
import { formatDateTime, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const DISPLAY: Record<BrokerCode, { name: string; phase?: number; portal: string }> = {
  upstox: { name: "Upstox", portal: "https://account.upstox.com/developer/apps" },
  dhan: { name: "Dhan", phase: 7, portal: "https://dhanhq.co/" },
};

function errorText(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof ApiRequestError) return err.message;
  return "Cannot reach the API.";
}

function SessionPill({ s }: { s: BrokerSessionStatus }) {
  if (s.status === "valid" && s.expires_at) {
    return <DataStateBadge state="live" detail={`valid until ${formatTime(s.expires_at)}`} />;
  }
  if (s.status === "revoked") return <DataStateBadge state="historical" detail="revoked" />;
  return <DataStateBadge state="disconnected" detail="login required" />;
}

function CopyButton({ value }: { value: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label="Copy redirect URI"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard blocked; the value is visible to select */
        }
      }}
    >
      {done ? <Check className="text-pnl-positive" /> : <Copy />}
    </Button>
  );
}

function CredentialsForm({ code, status }: { code: BrokerCode; status: BrokerSessionStatus }) {
  const upsert = useUpsertBrokerAccount(code);
  const [clientCode, setClientCode] = useState(status.client_code ?? "");
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [saved, setSaved] = useState(false);
  const redirectUri = `${API_URL}/api/v1/brokers/${code}/callback`;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(false);
    try {
      await upsert.mutateAsync({
        client_code: clientCode.trim(),
        api_key: apiKey || null,
        api_secret: apiSecret || null,
        label,
      });
      setApiKey("");
      setApiSecret("");
      setSaved(true);
    } catch {
      /* rendered below */
    }
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 border-t border-border-subtle pt-3">
      <div className="rounded-sm border border-border-subtle bg-panel-raised p-2 text-[11px] text-text-secondary">
        <p className="mb-1">
          Register this redirect URI in your {DISPLAY[code].name} developer app, then paste the
          app&apos;s API key and secret below. Secrets are encrypted at rest and never shown again.
        </p>
        <div className="flex items-center gap-1">
          <code className="tabular flex-1 truncate font-mono text-[11px] text-text-primary">
            {redirectUri}
          </code>
          <CopyButton value={redirectUri} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${code}-client`}>Client code</Label>
          <Input
            id={`${code}-client`}
            required
            value={clientCode}
            onChange={(e) => setClientCode(e.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${code}-label`}>Label (optional)</Label>
          <Input id={`${code}-label`} value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${code}-key`}>API key {status.configured && "(leave blank to keep)"}</Label>
          <Input
            id={`${code}-key`}
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${code}-secret`}>API secret {status.configured && "(leave blank to keep)"}</Label>
          <Input
            id={`${code}-secret`}
            type="password"
            autoComplete="off"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" disabled={upsert.isPending || !clientCode.trim()}>
          {upsert.isPending ? "Saving…" : "Save credentials"}
        </Button>
        {saved && (
          <span className="text-xs text-pnl-positive" role="status">
            Saved. Secrets cleared from this form.
          </span>
        )}
        {upsert.isError && (
          <span className="text-xs text-pnl-negative" role="alert">
            {errorText(upsert.error)}
          </span>
        )}
      </div>
    </form>
  );
}

export function BrokerCard({ status }: { status: BrokerSessionStatus }) {
  const code = status.broker;
  const meta = DISPLAY[code];
  const loginUrl = useBrokerLoginUrl(code);
  const revoke = useBrokerLogout(code);
  const [showCreds, setShowCreds] = useState(!status.configured);

  const onLogin = async () => {
    try {
      const r = await loginUrl.mutateAsync();
      // Full-page navigation to the broker's OAuth dialog; it redirects back to this page.
      window.location.assign(r.url);
    } catch {
      /* rendered below */
    }
  };

  return (
    <PanelCard
      title={meta.name}
      subtitle={status.client_code ? `Client ${status.client_code}` : "No account configured"}
      actions={<SessionPill s={status} />}
      bodyClassName="flex flex-col gap-3"
    >
      <dl className="grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <dt className="text-text-muted">Credentials</dt>
          <dd className={cn("font-medium", status.configured ? "text-text-primary" : "text-state-disconnected")}>
            {status.configured ? "Configured" : "Not configured"}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Token issued</dt>
          <dd className="tabular text-text-primary">
            {status.issued_at ? formatDateTime(status.issued_at) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-text-muted">Last checked</dt>
          <dd className="tabular text-text-primary">
            {status.last_checked_at ? formatDateTime(status.last_checked_at) : "—"}
          </dd>
        </div>
      </dl>

      <div className="flex flex-wrap items-center gap-2">
        {status.login_supported ? (
          <Button
            size="sm"
            onClick={onLogin}
            disabled={!status.configured || loginUrl.isPending}
            title={status.configured ? undefined : "Save API credentials first"}
          >
            <LogIn /> {loginUrl.isPending ? "Opening…" : `Log in to ${meta.name}`}
          </Button>
        ) : (
          <Button size="sm" disabled>
            <LogIn /> Ships in Phase {meta.phase}
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => revoke.mutate()}
          disabled={status.status !== "valid" || revoke.isPending}
        >
          <LogOut /> Revoke session
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setShowCreds((v) => !v)}>
          <KeyRound /> {showCreds ? "Hide credentials" : "API credentials"}
        </Button>
        <a
          href={meta.portal}
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex items-center gap-1 text-[11px] text-cyan-accent hover:underline"
        >
          Developer portal <ExternalLink className="size-3" />
        </a>
      </div>
      {(loginUrl.isError || revoke.isError) && (
        <p className="text-xs text-pnl-negative" role="alert">
          {errorText(loginUrl.error ?? revoke.error)}
        </p>
      )}

      {showCreds && <CredentialsForm key={status.client_code ?? ""} code={code} status={status} />}
    </PanelCard>
  );
}
