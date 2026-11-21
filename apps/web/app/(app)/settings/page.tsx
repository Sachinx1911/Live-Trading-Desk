import Link from "next/link";
import { Bell, Cable, KeyRound, Server, ShieldAlert, ShieldCheck, Sparkles, UserCircle, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const SECTIONS: { href: string; label: string; desc: string; icon: LucideIcon; phase?: number }[] = [
  { href: "/settings/brokers", label: "Brokers", desc: "Upstox / Dhan credentials and daily login", icon: KeyRound },
  { href: "/settings/providers", label: "Data providers", desc: "Active provider, comparison and failover", icon: Server, phase: 2 },
  { href: "/settings/notifications", label: "Notifications", desc: "Telegram alerts and in-app chips", icon: Bell },
  { href: "/settings/risk", label: "Risk limits", desc: "Per-trade risk, daily loss, kill switch", icon: ShieldAlert, phase: 3 },
  { href: "/settings/tools", label: "Tool server", desc: "jarvis service tokens and the tool-call log", icon: Cable },
  { href: "/settings/ai", label: "AI", desc: "LLM status, key location and the ADR-009 boundary", icon: Sparkles, phase: 6 },
  { href: "/settings/users", label: "Users", desc: "Operators and roles", icon: Users, phase: 10 },
  { href: "/settings/profile", label: "Profile", desc: "Display name and locale", icon: UserCircle, phase: 10 },
  { href: "/settings/security", label: "Security", desc: "Password and TOTP", icon: ShieldCheck, phase: 10 },
];

export default function Page() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {SECTIONS.map(({ href, label, desc, icon: Icon, phase }) => (
        <Link
          key={href}
          href={href}
          className="flex items-start gap-3 border border-border bg-pane p-3 transition-colors hover:border-border-strong hover:bg-raised"
        >
          <Icon className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-text-1">{label}</span>
              {phase && (
                <span className="rounded-sm border border-border px-1 text-[10px] text-text-3">
                  P{phase}
                </span>
              )}
            </div>
            <p className="text-[11px] text-text-3">{desc}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}
