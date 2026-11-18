"use client";

import { useEffect } from "react";
import { Label } from "@/components/ui/label";
import type { StrategyVersion } from "@/lib/api/generated";
import { useStrategies, useStrategyVersions } from "@/lib/api/trading";

const SEL = "h-8 rounded-sm border border-border-subtle bg-panel-raised px-2 text-xs";

/** Strategy → version selector shared by the backtest and optimisation forms. */
export function StrategyVersionPicker({
  strategyId,
  versionId,
  onStrategy,
  onVersion,
  idPrefix,
}: {
  strategyId: number | null;
  versionId: number | null;
  onStrategy: (id: number | null) => void;
  onVersion: (v: StrategyVersion | null) => void;
  idPrefix: string;
}) {
  const { data: strategies } = useStrategies(false);
  const { data: versions } = useStrategyVersions(strategyId);
  const eligible = (versions ?? []).filter((v) => v.status !== "rejected");

  // Default to the latest eligible version once versions load.
  useEffect(() => {
    if (!strategyId || !eligible.length) return;
    if (versionId == null || !eligible.some((v) => v.id === versionId)) onVersion(eligible[eligible.length - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId, versions]);

  return (
    <>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idPrefix}-strategy`}>Strategy</Label>
        <select
          id={`${idPrefix}-strategy`}
          value={strategyId ?? ""}
          onChange={(e) => {
            onStrategy(e.target.value ? Number(e.target.value) : null);
            onVersion(null);
          }}
          className={SEL}
        >
          <option value="">Select…</option>
          {strategies?.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${idPrefix}-version`}>Version</Label>
        <select
          id={`${idPrefix}-version`}
          value={versionId ?? ""}
          onChange={(e) => onVersion(eligible.find((v) => v.id === Number(e.target.value)) ?? null)}
          className={SEL}
          disabled={!strategyId}
        >
          {eligible.length === 0 && <option value="">No version</option>}
          {eligible.map((v) => (
            <option key={v.id} value={v.id}>
              v{v.version_no} · {v.status}{v.change_summary ? ` · ${v.change_summary}` : ""}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}
