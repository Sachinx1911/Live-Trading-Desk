"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { hasSession, subscribeSession } from "@/lib/api/client";
import { connectRealtime } from "@/lib/ws/store";

/**
 * Authenticated application frame. Redirects to /login when no session token exists.
 * Token validity is enforced by the API (401 → client redirects), not guessed here.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const authed = useSyncExternalStore(subscribeSession, hasSession, () => false);

  useEffect(() => {
    if (!authed) {
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
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
