"use client";

import type { OiStrikeOut } from "@/lib/api/generated";
import { formatNumber } from "@/lib/format";

/**
 * OI change by strike (Mark 1, 1.2), Sensibull-style: for each strike a call bar and a put bar
 * from a zero line, up for added OI, down for unwound OI. Calls in cyan, puts in amber (design
 * references, image 19: two sides, two colours; red stays reserved for danger). The ATM strike
 * is marked. A strike without OI at one end has no bar for that side: nothing is assumed.
 */
export function OiChangeChart({
  strikes,
  atm,
  width,
  height = 288,
}: {
  strikes: OiStrikeOut[];
  atm: number | null;
  /** Available width: strikes spread to fill it (never narrower than 34 px each). */
  width?: number;
  /** Total height including the strike labels. */
  height?: number;
}) {
  const max = Math.max(
    1,
    ...strikes.flatMap((s) => [Math.abs(s.call_change ?? 0), Math.abs(s.put_change ?? 0)]),
  );
  const STEP = width && strikes.length ? Math.max(34, Math.floor(width / strikes.length)) : 48;
  const W = Math.max(strikes.length * STEP, 320);
  const H = Math.max(120, height - 28);
  const mid = H / 2;
  const scale = (v: number) => (Math.abs(v) / max) * (mid - 18);
  const atmIndex =
    atm == null
      ? -1
      : strikes.reduce(
          (best, s, i) =>
            Math.abs(Number(s.strike) - atm) < Math.abs(Number(strikes[best]?.strike ?? Infinity) - atm)
              ? i
              : best,
          0,
        );

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H + 28}`}
        width={W}
        height={H + 28}
        role="img"
        aria-label="Open interest change by strike, calls and puts"
        className="block"
      >
        <line x1={0} x2={W} y1={mid} y2={mid} stroke="var(--border-strong)" strokeWidth={1} />
        {strikes.map((s, i) => {
          const x = i * STEP + Math.floor((STEP - 30) / 2) - 1; // 8 at the default 48 px step
          const call = s.call_change;
          const put = s.put_change;
          return (
            <g key={s.strike}>
              {i === atmIndex && (
                <rect x={i * STEP + 2} y={4} width={STEP - 4} height={H - 8} fill="var(--accent-soft)" opacity={0.6} />
              )}
              {call != null && call !== 0 && (
                <rect
                  x={x}
                  y={call > 0 ? mid - scale(call) : mid}
                  width={14}
                  height={Math.max(1, scale(call))}
                  fill="var(--accent)"
                >
                  <title>{`${s.strike} CE: ${call > 0 ? "+" : ""}${formatNumber(call)}`}</title>
                </rect>
              )}
              {put != null && put !== 0 && (
                <rect
                  x={x + 16}
                  y={put > 0 ? mid - scale(put) : mid}
                  width={14}
                  height={Math.max(1, scale(put))}
                  fill="var(--hud-amber)"
                >
                  <title>{`${s.strike} PE: ${put > 0 ? "+" : ""}${formatNumber(put)}`}</title>
                </rect>
              )}
              <text
                x={x + 15}
                y={H + 16}
                textAnchor="middle"
                className="font-mono"
                fontSize={10}
                fill={i === atmIndex ? "var(--accent-text)" : "var(--text-3)"}
              >
                {formatNumber(Number(s.strike))}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
