"use client";

import { usePathname } from "next/navigation";
import { LogOut, Server, User as UserIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { DataStateBadge } from "@/components/design";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { logout, useMe, useProviders } from "@/lib/api/queries";
import { formatTime } from "@/lib/format";
import { findNavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useRealtimeStore } from "@/lib/ws/store";

const SESSION_LABEL: Record<string, string> = {
  pre_open: "Pre-open",
  open: "Open",
  post_close: "Post-close",
  closed: "Closed",
  unknown: "Session unknown",
};

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const first = setTimeout(() => setNow(new Date()), 0);
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);
  return <span className="tabular font-mono text-xs text-text-secondary">{now ? formatTime(now) : "--:--:-- IST"}</span>;
}

function SessionIndicator() {
  const session = useRealtimeStore((s) => s.session);
  const wsState = useRealtimeStore((s) => s.wsState);
  const connected = wsState === "connected" && session.asOf !== null;
  return (
    <div className="flex items-center gap-2 rounded-sm border border-border-subtle bg-panel px-2 py-1">
      <span className="text-[11px] font-semibold text-text-primary">{session.exchange}</span>
      <span className={cn("text-[11px]", connected ? "text-text-secondary" : "text-text-muted")}>
        {connected ? SESSION_LABEL[session.state] : "Disconnected"}
      </span>
      <Clock />
    </div>
  );
}

function ProviderChip() {
  const { data, isError, isPending } = useProviders();
  if (isPending) return <DataStateBadge state="disconnected" detail="checking…" />;
  if (isError || !data || data.length === 0) {
    return <DataStateBadge state="disconnected" detail="no provider" />;
  }
  const primary = data[0];
  const state = primary.is_demo
    ? "demo"
    : primary.state === "connected"
      ? "live"
      : "disconnected";
  return <DataStateBadge state={state} detail={primary.display_name} />;
}

export function TopBar() {
  const pathname = usePathname();
  const item = findNavItem(pathname);
  const me = useMe();

  return (
    <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-border-subtle bg-panel px-4">
      <div className="flex min-w-0 items-center gap-3">
        <h1 className="truncate text-sm font-semibold text-text-primary">{item?.label ?? "Trading Platform"}</h1>
        {item?.phase && (
          <span className="rounded-sm border border-border-subtle px-1.5 text-[10px] text-text-muted">
            Ships in Phase {item.phase}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <SessionIndicator />
        <div className="flex items-center gap-1.5">
          <Server className="size-3.5 text-text-muted" aria-hidden />
          <ProviderChip />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" size="sm" className="gap-2 text-text-secondary">
                <UserIcon className="size-4" />
                <span className="max-w-32 truncate text-xs">{me.data?.email ?? "Account"}</span>
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="truncate text-xs">
              {me.data ? `${me.data.email} · ${me.data.roles.join(", ")}` : "Not signed in"}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="text-xs">
              <LogOut className="size-3.5" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
