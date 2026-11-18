"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { PanelCard } from "@/components/design";
import { VisualBuilder } from "@/components/strategies/builder/VisualBuilder";
import { Skeleton } from "@/components/ui/skeleton";

function Inner() {
  const params = useSearchParams();
  const from = params.get("from");
  return <VisualBuilder from={from} />;
}

export default function Page() {
  return (
    <PanelCard
      title="Visual Strategy Builder"
      subtitle="Build a DSL v1 strategy from forms — no code. Validate on the server before saving."
      actions={<Link href="/strategies" className="text-[11px] text-accent-cyan">Back to library</Link>}
      bodyClassName="p-3"
    >
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <Inner />
      </Suspense>
    </PanelCard>
  );
}
