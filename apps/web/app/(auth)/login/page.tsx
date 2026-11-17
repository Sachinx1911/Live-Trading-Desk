"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiRequestError } from "@/lib/api/client";
import { useLogin } from "@/lib/api/queries";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login.mutateAsync({ email, password });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") ? next : "/dashboard");
    } catch {
      /* error rendered below */
    }
  };

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
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Password</Label>
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
        <p role="alert" className="text-xs text-pnl-negative">
          {message}
        </p>
      )}
      <Button type="submit" disabled={login.isPending} className="mt-1">
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-app p-6">
      <div className="w-full max-w-sm rounded-md border border-border-subtle bg-panel p-6">
        <div className="mb-6 flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-sm bg-cyan-accent/15 font-mono text-xs font-bold text-cyan-accent">
            TP
          </span>
          <div>
            <h1 className="text-sm font-semibold text-text-primary">Trading Platform</h1>
            <p className="text-[11px] text-text-muted">Sign in to your terminal</p>
          </div>
        </div>
        <Suspense>
          <LoginForm />
        </Suspense>
        <p className="mt-6 text-[11px] text-text-muted">
          No public sign-up. Accounts are created by the operator CLI.
        </p>
      </div>
    </div>
  );
}
