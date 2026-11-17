/**
 * Formatting helpers. Money is never formatted inline in components.
 * INR uses Indian digit grouping: ₹1,00,000.00. Storage is UTC; display is IST by default.
 */

const inrFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrWhole = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export function formatMoney(
  value: number,
  opts: { currency?: string; whole?: boolean } = {},
): string {
  const { currency = "INR", whole = false } = opts;
  if (currency === "INR") return (whole ? inrWhole : inrFormatter).format(value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  }).format(value);
}

/** Signed money for P&L: +₹2,450.00 / −₹1,120.50 (true minus sign). */
export function formatSignedMoney(value: number, currency = "INR"): string {
  const abs = formatMoney(Math.abs(value), { currency });
  if (value > 0) return `+${abs}`;
  if (value < 0) return `−${abs}`;
  return abs;
}

export function formatPct(value: number, digits = 2, signed = true): string {
  const abs = Math.abs(value).toFixed(digits) + "%";
  if (!signed) return value.toFixed(digits) + "%";
  if (value > 0) return `+${abs}`;
  if (value < 0) return `−${abs}`;
  return abs;
}

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export const IST = "Asia/Kolkata";

export function formatTime(iso: string | Date, zone: string = IST): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const s = new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: zone,
  }).format(d);
  return `${s} ${zoneLabel(zone)}`;
}

export function formatDateTime(iso: string | Date, zone: string = IST): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const s = new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: zone,
  }).format(d);
  return `${s} ${zoneLabel(zone)}`;
}

export function zoneLabel(zone: string): string {
  return zone === IST ? "IST" : zone;
}

/** Human age like "12s", "3m", "2h". */
export function formatAge(iso: string | Date, now: Date = new Date()): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const sec = Math.max(0, Math.round((now.getTime() - d.getTime()) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}
