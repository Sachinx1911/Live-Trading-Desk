"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { hasSession, subscribeSession, tryDevLogin } from "@/lib/api/client";
import { connectRealtime } from "@/lib/ws/store";

const RETRY_MS = 3000;

/**
 * Session guard shared by the app shell and the chrome-less panels (Stage 4.4).
 * With no session token it first tries the API's development-only /auth/dev-login
 * (DEV_AUTO_LOGIN_EMAIL). If the API is not reachable yet (starting, restarting) it says so and
 * retries every 3 s instead of showing the login page; only when the API answers that dev login
 * is off does it redirect to /login (keeping path and query, so a panel URL survives login).
 * Token validity is enforced by the API (401 → client signs in again or redirects).
 * Once signed in it opens the realtime connection.
 */
export function SessionGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const authed = useSyncExternalStore(subscribeSession, hasSession, () => false);
  const [apiDown, setApiDown] = useState(false);

  useEffect(() => {
    // During hydration `authed` is the server snapshot (false); re-read the real session
    // here so a full page load with a stored token does not bounce to /login.
    if (!hasSession()) {
      let cancelled = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const attempt = () => {
        void tryDevLogin().then((r) => {
          if (cancelled) return;
          // "ok" stores tokens, which notifies subscribers and re-runs this effect.
          if (r === "ok") return;
          if (r === "off") {
            const here = `${window.location.pathname}${window.location.search}`;
            router.replace(`/login?next=${encodeURIComponent(here)}`);
            return;
          }
          setApiDown(true);
          timer = setTimeout(attempt, RETRY_MS);
        });
      };
      attempt();
      return () => {
        cancelled = true;
        if (timer) clearTimeout(timer);
      };
    }
    if (!authed) return;
    return connectRealtime();
  }, [authed, router]);

  if (!authed) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-2 px-4 text-center text-[13px] text-text-3" role="status">
        <span className="hud-label text-accent-text">{apiDown ? "Connecting to the API" : "Checking session"}</span>
        {apiDown && <span>API not reachable yet (starting or stopped). Retrying every 3 seconds…</span>}
      </div>
    );
  }
  return <>{children}</>;
}
