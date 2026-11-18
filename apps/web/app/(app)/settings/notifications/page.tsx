import { PanelCard } from "@/components/design";

const ALERTS: { when: string; what: string; level: string }[] = [
  { when: "08:15 IST, then every 30 min in session", what: "Broker token missing or expired, with the login link", level: "warning" },
  { when: "During session", what: "Market data feed disconnected or reconnecting", level: "warning" },
  { when: "Any time", what: "Kill switch engaged (global, account or strategy)", level: "critical" },
  { when: "Every 60 s in session", what: "Broker reconciliation mismatch; live trading paused", level: "critical" },
  { when: "After close", what: "Daily summary: P&L vs limits, rule violations, data gaps", level: "info" },
];

export default function Page() {
  return (
    <div className="flex flex-col gap-3">
      <PanelCard title="Telegram" subtitle="Configured on the server" bodyClassName="text-xs text-text-2">
        <p>
          Alerts are sent by the worker through a Telegram bot configured with{" "}
          <code className="font-mono text-text-1">TELEGRAM_BOT_TOKEN</code> and{" "}
          <code className="font-mono text-text-1">TELEGRAM_CHAT_ID</code> in the server&apos;s{" "}
          <code className="font-mono text-text-1">.env</code>. Tokens are never entered here.
        </p>
        <p className="mt-2 text-text-3">
          Status unknown from the browser: the API does not yet report whether Telegram is
          configured. When it is not, alerts are written to the server log instead.
        </p>
      </PanelCard>
      <PanelCard title="Alert types" bodyClassName="p-0">
        <table className="w-full text-xs">
          <thead className="text-[11px] uppercase tracking-wide text-text-3">
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left font-medium">When</th>
              <th className="px-3 py-2 text-left font-medium">Alert</th>
              <th className="px-3 py-2 text-left font-medium">Level</th>
            </tr>
          </thead>
          <tbody>
            {ALERTS.map((a) => (
              <tr key={a.what} className="border-b border-border last:border-0">
                <td className="px-3 py-2 text-text-2">{a.when}</td>
                <td className="px-3 py-2 text-text-1">{a.what}</td>
                <td className="px-3 py-2 font-mono text-[11px] uppercase text-text-3">{a.level}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
      <PanelCard title="In-app" bodyClassName="text-xs text-text-2">
        The same conditions show in the top bar: provider state, broker session and market
        session chips. Nothing is marked Live unless a connected provider is streaming.
      </PanelCard>
    </div>
  );
}
