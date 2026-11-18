"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { KeyRound, LogOut, Search, Server, User as UserIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ThemeMenuItems } from "@/components/layout/ThemeControl";
import { InstrumentSearch } from "@/components/market/InstrumentSearch";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { logout, useBrokers, useMe, useProviders } from "@/lib/api/queries";
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
  return <span className="tabular text-[12px] text-text-3">{now ? formatTime(now) : "--:--:-- IST"}</span>;
}

/** 28px pill with a coloured dot, the TradingView status idiom. */
function Pill({
  dot,
  children,
  className,
  href,
  title,
}: {
  dot?: "up" | "down" | "warn" | "ai" | "muted";
  children: React.ReactNode;
  className?: string;
  href?: string;
  title?: string;
}) {
  const dotClass =
    dot === "up" ? "bg-up" : dot === "down" ? "bg-down" : dot === "warn" ? "bg-warn" : dot === "ai" ? "bg-ai" : "bg-text-3";
  const inner = (
    <span
      className={cn("inline-flex h-7 shrink-0 items-center gap-2 whitespace-nowrap rounded-[var(--r-pill)] bg-raised px-3 text-[13px] text-text-2", href && "hover:bg-raised-hover", className)}
      title={title}
    >
      {dot && <span className={cn("size-1.5 shrink-0 rounded-full", dotClass)} aria-hidden />}
      {children}
    </span>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

function SessionPill() {
  const session = useRealtimeStore((s) => s.session);
  const wsState = useRealtimeStore((s) => s.wsState);
  const connected = wsState === "connected" && session.asOf !== null;
  const open = connected && session.state === "open";
  return (
    <Pill dot={!connected ? "down" : open ? "up" : "muted"}>
      <span className="font-semibold text-text-1">{session.exchange}</span>
      <span>{connected ? SESSION_LABEL[session.state] : "Disconnected"}</span>
      <Clock />
    </Pill>
  );
}

function ProviderPill() {
  const { data, isError, isPending } = useProviders();
  if (isPending) return <Pill dot="muted">Provider…</Pill>;
  if (isError || !data || data.length === 0) return <Pill dot="down">No provider</Pill>;
  const primary = data[0];
  const state = primary.is_demo ? "demo" : primary.state === "connected" ? "live" : "disconnected";
  return (
    <Pill dot={state === "live" ? "up" : state === "demo" ? "ai" : "down"} href="/market/providers" title="Data providers">
      <Server className="size-3.5 text-text-3" aria-hidden />
      {primary.display_name}
      {state === "demo" && <span className="text-[11px] uppercase text-ai">demo</span>}
    </Pill>
  );
}

function BrokerPill() {
  const { data } = useBrokers();
  const upstox = data?.find((b) => b.broker === "upstox");
  if (!upstox || !upstox.configured) return null;
  const valid = upstox.status === "valid";
  return (
    <Pill dot={valid ? "up" : "down"} href="/settings/brokers" title={valid ? "Broker session valid" : "Broker login required"}>
      <KeyRound className="size-3.5 text-text-3" aria-hidden />
      {valid ? "Upstox session" : "Login required"}
    </Pill>
  );
}

/** Symbol search pill: expands into the instrument search and jumps to the market page. */
function SymbolSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      {open ? (
        <div className="w-72">
          <InstrumentSearch
            placeholder="Symbol search…"
            onPick={(i) => {
              setOpen(false);
              router.push(`/market?instrument=${i.instrument_id}`);
            }}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-7 w-56 items-center gap-2 rounded-[var(--r-pill)] bg-raised px-3 text-[13px] text-text-3 hover:bg-raised-hover hover:text-text-2"
          aria-label="Symbol search"
        >
          <Search className="size-3.5" aria-hidden />
          <span className="truncate">Search symbol</span>
        </button>
      )}
    </div>
  );
}

export function TopBar() {
  const pathname = usePathname();
  const item = findNavItem(pathname);
  const me = useMe();

  return (
    <header className="flex h-[var(--h-toolbar)] shrink-0 items-center justify-between gap-4 border-b border-border bg-pane px-3">
      <div className="flex min-w-0 items-center gap-3">
        <Link href="/dashboard" className="flex items-center gap-2" aria-label="Dashboard">
          <span className="flex size-6 items-center justify-center rounded-[var(--r-sm)] bg-accent text-[11px] font-bold text-white">TP</span>
        </Link>
        <h1 className="truncate text-[14px] font-semibold text-text-1">{item?.label ?? "Trading Platform"}</h1>
        <SymbolSearch />
      </div>
      <div className="flex items-center gap-2">
        <SessionPill />
        <ProviderPill />
        <BrokerPill />
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" size="sm" className="gap-2 text-text-2">
                <UserIcon className="size-4" />
                <span className="max-w-32 truncate text-[13px]">{me.data?.email ?? "Account"}</span>
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel className="truncate">
              {me.data ? `${me.data.email} · ${me.data.roles.join(", ")}` : "Not signed in"}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <ThemeMenuItems />
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout}>
              <LogOut className="size-3.5" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
