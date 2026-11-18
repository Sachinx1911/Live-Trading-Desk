"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { hasSession, subscribeSession, tryDevLogin } from "@/lib/api/client";
import { connectRealtime } from "@/lib/ws/store";

/**
 * Authenticated application frame. With no session token it first tries the API's
 * development-only /auth/dev-login (DEV_AUTO_LOGIN_EMAIL); when that is off it redirects to
 * /login. Token validity is enforced by the API (401 → client redirects), not guessed here.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const authed = useSyncExternalStore(subscribeSession, hasSession, () => false);

  useEffect(() => {
    // During hydration `authed` is the server snapshot (false); re-read the real session
    // here so a full page load with a stored token does not bounce to /login.
    if (!hasSession()) {
      let cancelled = false;
      void tryDevLogin().then((ok) => {
        // Success stores tokens, which notifies subscribers and re-runs this effect.
        if (!cancelled && !ok) {
          router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        }
      });
      return () => {
        cancelled = true;
      };
    }
    if (!authed) return;
    return connectRealtime();
  }, [authed, router]);

  if (!authed) {
    return <div className="flex h-dvh items-center justify-center text-xs text-text-muted">Checking session…</div>;
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-app">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-y-auto p-4">{children}</main>
      </div>
    </div>
  );
}
