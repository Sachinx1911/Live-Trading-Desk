import { SessionGate } from "@/components/layout/SessionGate";

/**
 * Chrome-less panel windows (Mark 1 Stage 4.4, docs/panels.md): no sidebar or top bar, same
 * session handling and HUD theme as the app. Each page renders a PanelFrame that fills the
 * window. Panels are read-only views.
 */
export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return <SessionGate>{children}</SessionGate>;
}
