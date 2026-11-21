import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  Bell,
  BookOpenCheck,
  Bot,
  BrainCircuit,
  CandlestickChart,
  FileText,
  FlaskConical,
  Globe2,
  History,
  ListChecks,
  LayoutDashboard,
  Newspaper,
  Radar,
  Settings,
  Wallet,
  Wrench,
  Zap,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Phase in which this screen ships. Undefined = shipped in Phase 1 shell. */
  phase?: number;
  /** Live trading is tinted and hidden until a broker is connected. */
  live?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

/** Sidebar groups per docs/architecture/06-ui-page-map.md §2. All 15 master-prompt items. */
export const NAV_GROUPS: NavGroup[] = [
  { label: "Overview", items: [{ label: "Dashboard", href: "/dashboard", icon: LayoutDashboard }] },
  {
    label: "Intelligence",
    items: [
      { label: "AI Trading Hub", href: "/ai-hub", icon: Bot, phase: 6 },
      { label: "AI Learning", href: "/ai-learning", icon: BrainCircuit, phase: 6 },
    ],
  },
  {
    label: "Strategy",
    items: [{ label: "Strategy Center", href: "/strategies", icon: FlaskConical, phase: 5 }],
  },
  {
    label: "Data",
    items: [
      { label: "Market Data", href: "/market", icon: CandlestickChart, phase: 2 },
      { label: "OI Change", href: "/market/oi-change", icon: BarChart3 },
      { label: "Market Scanner", href: "/scanner", icon: Radar, phase: 5 },
      { label: "News", href: "/news", icon: Newspaper },
    ],
  },
  {
    label: "Trading",
    items: [
      { label: "Trading", href: "/trading", icon: Activity, phase: 3 },
      { label: "Paper Trading", href: "/paper", icon: BookOpenCheck, phase: 3 },
      { label: "Live Trading", href: "/live", icon: Zap, phase: 10, live: true },
    ],
  },
  {
    label: "Research",
    items: [
      { label: "Backtesting", href: "/backtesting", icon: BarChart3, phase: 4 },
      { label: "Replay", href: "/replay", icon: History, phase: 4 },
    ],
  },
  {
    label: "Portfolio",
    items: [
      { label: "Portfolio & Analytics", href: "/portfolio", icon: Wallet, phase: 3 },
      { label: "Reports", href: "/reports", icon: FileText, phase: 3 },
    ],
  },
  {
    label: "System",
    items: [
      { label: "Protocols", href: "/protocols", icon: ListChecks },
      { label: "Alerts", href: "/alerts", icon: Bell },
      { label: "Multi-Market", href: "/multi-market", icon: Globe2 },
      { label: "Tools", href: "/tools", icon: Wrench, phase: 2 },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

export function findNavItem(pathname: string): NavItem | undefined {
  return ALL_NAV_ITEMS.find((i) => pathname === i.href || pathname.startsWith(i.href + "/"));
}
