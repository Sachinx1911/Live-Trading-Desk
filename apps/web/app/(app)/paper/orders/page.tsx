"use client";

import { useState } from "react";
import { PanelCard } from "@/components/design";
import { OrdersTable } from "@/components/trading/OrdersTable";
import { PaperHeader } from "@/components/trading/PaperHeader";
import { usePaperOrders } from "@/lib/api/trading";

function Orders({ accountId }: { accountId: number }) {
  const [openOnly, setOpenOnly] = useState(false);
  const { data, isPending } = usePaperOrders(accountId, openOnly);
  return (
    <PanelCard
      title="Orders"
      subtitle="Every order the simulator accepted, with its state transitions"
      bodyClassName="overflow-x-auto p-0"
      actions={
        <label className="flex items-center gap-1 text-[11px] text-text-2">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> open only
        </label>
      }
    >
      <OrdersTable orders={data} isPending={isPending} />
    </PanelCard>
  );
}

export default function PaperOrdersPage() {
  return <PaperHeader>{(id) => <Orders accountId={id} />}</PaperHeader>;
}
