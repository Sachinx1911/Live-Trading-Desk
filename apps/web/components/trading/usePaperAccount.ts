"use client";

import { useEffect } from "react";
import type { PaperAccount } from "@/lib/api/generated";
import { usePaperAccounts } from "@/lib/api/trading";
import { usePaperSelection } from "@/lib/paper-store";

/** Selected paper account (persisted) or the first one; null while loading or when none. */
export function usePaperAccount(): {
  accounts: PaperAccount[] | undefined;
  account: PaperAccount | null;
  accountId: number | null;
  select: (id: number | null) => void;
  isPending: boolean;
  isError: boolean;
} {
  const { data, isPending, isError } = usePaperAccounts();
  const accountId = usePaperSelection((s) => s.accountId);
  const select = usePaperSelection((s) => s.select);
  const account = data?.find((a) => a.id === accountId) ?? data?.[0] ?? null;
  useEffect(() => {
    if (account && account.id !== accountId) select(account.id);
  }, [account, accountId, select]);
  return { accounts: data, account, accountId: account?.id ?? null, select, isPending, isError };
}
