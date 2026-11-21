"use client";

import { Sidebar } from "./Sidebar";
import { SessionGate } from "./SessionGate";
import { TopBar } from "./TopBar";

/**
 * Authenticated application frame: sidebar, top bar and the scrolling page area.
 * Session handling (dev auto-login, API-down retry, login redirect, realtime connection)
 * lives in SessionGate, shared with the chrome-less panels under /panel.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SessionGate>
      <div className="flex h-dvh overflow-hidden">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <main className="min-h-0 flex-1 overflow-y-auto p-3">{children}</main>
        </div>
      </div>
    </SessionGate>
  );
}
