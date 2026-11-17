"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { NAV_GROUPS, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUiStore } from "@/components/layout/ui-store";

function NavLink({ item, collapsed, active }: { item: NavItem; collapsed: boolean; active: boolean }) {
  const Icon = item.icon;
  const link = (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex h-8 items-center gap-2.5 rounded-sm px-2 text-[13px] text-sidebar-foreground outline-none transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring/60",
        active && "bg-sidebar-accent text-cyan-accent",
        item.live && "text-mode-live/80 hover:text-mode-live",
        item.live && active && "text-mode-live",
        collapsed && "justify-center px-0",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      {!collapsed && <span className="truncate">{item.label}</span>}
      {!collapsed && item.phase && (
        <span className="ml-auto rounded-sm border border-border-subtle px-1 text-[10px] tabular text-text-muted">
          P{item.phase}
        </span>
      )}
    </Link>
  );
  if (!collapsed) return link;
  return (
    <Tooltip>
      <TooltipTrigger render={link} />
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-150",
        collapsed ? "w-14" : "w-56",
      )}
      aria-label="Primary navigation"
    >
      <div className={cn("flex h-12 items-center border-b border-sidebar-border px-3", collapsed && "justify-center px-0")}>
        <div className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-sm bg-cyan-accent/15 font-mono text-[11px] font-bold text-cyan-accent">
            TP
          </span>
          {!collapsed && (
            <span className="text-xs font-semibold tracking-wide text-text-primary">Trading Platform</span>
          )}
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-3">
            {!collapsed ? (
              <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                {group.label}
              </p>
            ) : (
              <div className="mx-2 mb-1 border-t border-sidebar-border" aria-hidden />
            )}
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.href}>
                  <NavLink
                    item={item}
                    collapsed={collapsed}
                    active={pathname === item.href || pathname.startsWith(item.href + "/")}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <button
        type="button"
        onClick={toggle}
        className="flex h-10 items-center justify-center gap-2 border-t border-sidebar-border text-[11px] text-text-muted hover:text-text-primary"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
        {!collapsed && "Collapse"}
      </button>
    </aside>
  );
}
