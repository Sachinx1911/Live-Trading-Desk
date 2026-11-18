"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { EmptyState, PanelCard } from "@/components/design";
import { cn } from "@/lib/utils";
import { AccountPicker, CreateAccountForm } from "./AccountPicker";
import { usePaperAccount } from "./usePaperAccount";

const TABS = [
  { href: "/paper", label: "Overview" },
  { href: "/paper/orders", label: "Orders" },
  { href: "/paper/positions", label: "Positions & trades" },
];

/** Shared header for /paper/*: account picker, tabs; renders the create form when no account exists. */
export function PaperHeader({ children }: { children: (accountId: number) => React.ReactNode }) {
  const pathname = usePathname();
  const { accounts, accountId, isPending, isError, select } = usePaperAccount();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "rounded-sm px-2 py-1 text-xs",
                pathname === t.href ? "bg-raised text-text-1" : "text-text-2 hover:text-text-1",
              )}
            >
              {t.label}
            </Link>
          ))}
        </nav>
        <AccountPicker />
      </div>
      {isPending ? (
        <EmptyState title="Loading paper accounts…" />
      ) : isError ? (
        <EmptyState title="Cannot reach the API" description="Paper trading data is unavailable." />
      ) : !accounts || accounts.length === 0 ? (
        <PanelCard title="Create your first paper account" subtitle="Virtual capital only. Default ₹1,00,000 (master prompt); change it any time.">
          <CreateAccountForm onDone={(id) => select(id)} compact />
        </PanelCard>
      ) : accountId != null ? (
        children(accountId)
      ) : null}
    </div>
  );
}
