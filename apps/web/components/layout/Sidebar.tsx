"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { NAV_GROUPS, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUiStore } from "@/components/layout/ui-store";

/*
 * Icon rail per the TradingView reference (§5): 52px black rail, 36px icon buttons, active
 * item on a #303030 pill, groups separated by 1px lines. Expands to 220px with labels.
 */
function NavLink({ item, collapsed, active }: { item: NavItem; collapsed: boolean; active: boolean }) {
  const Icon = item.icon;
  const link = (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex h-9 items-center gap-3 rounded-[var(--r-sm)] text-[14px] outline-none transition-colors",
        "text-text-3 hover:bg-hover hover:text-text-1 focus-visible:ring-1 focus-visible:ring-ring",
        active && "bg-raised text-text-1",
        item.live && !active && "text-down/70 hover:text-down",
        item.live && active && "text-down",
        collapsed ? "mx-2 size-9 justify-center" : "mx-2 px-2.5",
      )}
    >
      <Icon className="size-[18px] shrink-0" aria-hidden />
      {!collapsed && <span className="truncate">{item.label}</span>}
      {!collapsed && item.phase && (
        <span className="ml-auto rounded-full bg-app px-1.5 text-[10px] tabular text-text-3">P{item.phase}</span>
      )}
    </Link>
  );
  if (!collapsed) return link;
  return (
    <Tooltip>
      <TooltipTrigger render={link} />
      <TooltipContent side="right" className="flex items-center gap-2">
        {item.label}
        {item.phase && <span className="text-[10px] text-text-3">Phase {item.phase}</span>}
      </TooltipContent>
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
        "flex h-full shrink-0 flex-col border-r border-border bg-pane transition-[width] duration-150",
        collapsed ? "w-[52px]" : "w-[220px]",
      )}
      aria-label="Primary navigation"
    >
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.label}>
            {gi > 0 && <div className="mx-3 my-1.5 border-t border-border" aria-hidden />}
            {!collapsed && (
              <p className="px-5 pt-1 pb-0.5 text-[11px] font-medium uppercase tracking-wide text-text-3">
                {group.label}
              </p>
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
        className="flex h-9 items-center justify-center gap-2 border-t border-border text-[12px] text-text-3 hover:bg-hover hover:text-text-1"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
        {!collapsed && "Collapse"}
      </button>
    </aside>
  );
}
