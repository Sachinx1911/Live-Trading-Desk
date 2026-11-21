"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiRequestError, tryDevLogin } from "@/lib/api/client";
import { useLogin } from "@/lib/api/queries";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // With dev auto-login on (local development only) the form is never needed: sign in and
  // go on. The form shows only when the API says dev login is off.
  const [checking, setChecking] = useState(true);

  const goNext = () => {
    const next = params.get("next");
    router.replace(next && next.startsWith("/") ? next : "/dashboard");
  };

  useEffect(() => {
    let cancelled = false;
    void tryDevLogin().then((r) => {
      if (cancelled) return;
      if (r === "ok" || r === "unreachable") {
        // unreachable: AppShell waits for the API and retries; no login form for that.
        const next = params.get("next");
        router.replace(next && next.startsWith("/") ? next : "/dashboard");
        return;
      }
      setChecking(false);
    });
    return () => {
      cancelled = true;
    };
  }, [params, router]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login.mutateAsync({ email, password });
      goNext();
    } catch {
      /* error rendered below */
    }
  };

  if (checking) {
    return (
      <p role="status" className="hud-label text-accent-text">
        Signing in…
      </p>
    );
  }

  const err = login.error;
  const message =
    err instanceof ApiRequestError
      ? err.status === 401
        ? "Invalid email or password."
        : err.message
      : err
        ? "Cannot reach the API. Is the backend running?"
        : null;

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email" className="text-[13px] text-text-2">
          Email
        </Label>
        <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password" className="text-[13px] text-text-2">
          Password
        </Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {message && (
        <p role="alert" className="text-[13px] text-down">
          {message}
        </p>
      )}
      <Button type="submit" variant="primary" size="lg" disabled={login.isPending} className="mt-1 w-full">
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="glass w-full max-w-[360px] rounded-[var(--r-lg)] p-7">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex size-8 items-center justify-center rounded-full border border-accent bg-accent-soft font-mono text-[12px] font-bold text-accent-text hud-glow">TP</span>
          <div>
            <h1 className="text-[16px] font-semibold text-text-1">Trading Platform</h1>
            <p className="text-[12px] text-text-3">Sign in to your terminal</p>
          </div>
        </div>
        <Suspense>
          <LoginForm />
        </Suspense>
        <p className="mt-6 text-[12px] text-text-3">No public sign-up. Accounts are created by the operator CLI.</p>
      </div>
    </div>
  );
}
