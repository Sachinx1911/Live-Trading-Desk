import { panelRegistry } from "@/lib/panels";

/**
 * Panel discovery for jarvis (Mark 1 Stage 4.4): every panel, its path, parameters and sizing
 * hints. Static (built from lib/panels.ts); contains no data and no secrets.
 */
export function GET() {
  return Response.json(panelRegistry());
}
