"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { NAV_GROUPS, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUiStore } from "@/components/layout/ui-store";

/*
 * Icon rail (52px, expands to 220px with labels). HUD style: active item lit in cyan with a
 * 2px edge, group labels as monospaced uppercase, groups separated by hairlines.
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
        active && "bg-accent-soft text-accent-text shadow-[inset_2px_0_0_var(--accent)]",
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
  // The most specific matching item is active (/market/oi-change must not also light /market).
  const activeHref = NAV_GROUPS.flatMap((g) => g.items)
    .filter((i) => pathname === i.href || pathname.startsWith(i.href + "/"))
    .reduce<string | null>((best, i) => (best == null || i.href.length > best.length ? i.href : best), null);

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
              <p className="hud-label px-5 pt-1 pb-0.5 text-[10px] text-text-3">
                {group.label}
              </p>
            )}
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.href}>
                  <NavLink
                    item={item}
                    collapsed={collapsed}
                    active={item.href === activeHref}
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
