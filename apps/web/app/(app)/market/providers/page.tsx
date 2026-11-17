import { ProviderStatusPanel } from "@/components/dashboard/ProviderStatusPanel";
import { CollectorCard } from "@/components/market/CollectorCard";
import { CoverageTable } from "@/components/market/CoverageTable";

export default function MarketProvidersPage() {
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-12 xl:col-span-5">
        <ProviderStatusPanel />
      </div>
      <div className="col-span-12 xl:col-span-7">
        <CollectorCard />
      </div>
      <div className="col-span-12">
        <CoverageTable />
      </div>
    </div>
  );
}
