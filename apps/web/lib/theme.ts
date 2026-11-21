/**
 * Theme resolution shared by the pre-paint inline script (app/layout.tsx), the ThemeSync
 * component and the charts. `data-theme` on <html> is the single source of truth at runtime.
 */
export type ThemePreference = "dark" | "light" | "system";
export type ResolvedTheme = "dark" | "light";

export const THEME_STORAGE_KEY = "tp.ui";
const MEDIA = "(prefers-color-scheme: dark)";

export function resolveTheme(pref: ThemePreference): ResolvedTheme {
  if (pref === "system") {
    if (typeof window === "undefined") return "dark";
    return window.matchMedia(MEDIA).matches ? "dark" : "light";
  }
  return pref;
}

/** Writes data-theme + the legacy `dark` class + <meta name="color-scheme">. */
export function applyTheme(resolved: ResolvedTheme) {
  if (typeof document === "undefined") return;
  const html = document.documentElement;
  if (html.dataset.theme === resolved) return;
  html.dataset.theme = resolved;
  html.classList.toggle("dark", resolved === "dark");
  let meta = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "color-scheme";
    document.head.appendChild(meta);
  }
  meta.content = resolved;
}

export function currentTheme(): ResolvedTheme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/** Subscribe to theme changes (data-theme mutations). Returns an unsubscribe. */
export function onThemeChange(cb: (t: ResolvedTheme) => void): () => void {
  if (typeof document === "undefined") return () => {};
  const obs = new MutationObserver(() => cb(currentTheme()));
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
}

export function watchSystemTheme(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const mq = window.matchMedia(MEDIA);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

/** CSS variable snapshot for canvas charts (Lightweight Charts cannot read var()). */
export function chartPalette() {
  const fallback = {
    bg: "#0a1220",
    text: "#94c3da",
    grid: "rgba(95,212,255,0.05)",
    border: "#1f4a6b",
    crosshair: "#5fd4ff",
    crosshairLabel: "#10213a",
    up: "#1fb893",
    down: "#ff4d4d",
    priceLine: "#94c3da",
    accent: "#5fd4ff",
  };
  if (typeof document === "undefined") return fallback;
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fb: string) => cs.getPropertyValue(name).trim() || fb;
  return {
    bg: v("--bg-pane", fallback.bg),
    text: v("--chart-text", fallback.text),
    grid: v("--chart-grid", fallback.grid),
    border: v("--border-strong", fallback.border),
    crosshair: v("--chart-crosshair", fallback.crosshair),
    crosshairLabel: v("--bg-raised", fallback.crosshairLabel),
    up: v("--up-candle", fallback.up),
    down: v("--down", fallback.down),
    priceLine: v("--text-2", fallback.priceLine),
    accent: v("--accent", fallback.accent),
  };
}

/**
 * Inline, dependency-free script run before first paint. Keep in sync with resolveTheme /
 * applyTheme: reads the persisted zustand store (`tp.ui` → state.theme).
 */
export const PRE_PAINT_SCRIPT = `(function(){try{var p="dark";var raw=localStorage.getItem("${THEME_STORAGE_KEY}");if(raw){var st=JSON.parse(raw);var t=st&&st.state&&st.state.theme;if(t==="light"||t==="dark"||t==="system")p=t;}var r=p==="system"?(window.matchMedia("${MEDIA}").matches?"dark":"light"):p;var h=document.documentElement;h.setAttribute("data-theme",r);if(r==="dark")h.classList.add("dark");else h.classList.remove("dark");var m=document.querySelector('meta[name="color-scheme"]');if(!m){m=document.createElement("meta");m.name="color-scheme";document.head.appendChild(m);}m.content=r;}catch(e){}})();`;

/** `#rrggbb` → `rgba(r,g,b,a)`; canvas fillStyle does not reliably parse color-mix(). */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}
