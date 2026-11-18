"use client";

/** Dense form primitives for the visual builder (TradingView-style 28–32px controls). */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const SEL = "h-7 border border-border bg-raised px-1.5 text-[11px] text-text-1 outline-none focus:border-accent";
export const INP = "h-7 border border-border bg-raised px-1.5 text-[11px] text-text-1 outline-none focus:border-accent";

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-1", className)}>
      <span className="text-[10px] uppercase tracking-wide text-text-3">{label}</span>
      {children}
      {hint && <span className="text-[10px] text-text-3">{hint}</span>}
    </label>
  );
}

export function Select({ value, onChange, options, labels, className, allowBlank }: {
  value: string | null | undefined;
  onChange: (v: string) => void;
  options: readonly string[];
  labels?: Record<string, string>;
  className?: string;
  allowBlank?: string;
}) {
  return (
    <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} className={cn(SEL, className)}>
      {allowBlank !== undefined && <option value="">{allowBlank}</option>}
      {options.map((o) => (
        <option key={o} value={o}>{labels?.[o] ?? o}</option>
      ))}
    </select>
  );
}

export function NumberInput({ value, onChange, className, step, min, max, placeholder, allowBlank }: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  className?: string;
  step?: number | "any";
  min?: number;
  max?: number;
  placeholder?: string;
  allowBlank?: boolean;
}) {
  return (
    <input
      type="number"
      value={value ?? ""}
      step={step ?? "any"}
      min={min}
      max={max}
      placeholder={placeholder}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw === "") { onChange(allowBlank ? null : 0); return; }
        const n = Number(raw);
        if (!Number.isNaN(n)) onChange(n);
      }}
      className={cn(INP, "w-20", className)}
    />
  );
}

export function TextInput({ value, onChange, className, placeholder, maxLength }: {
  value: string | null | undefined;
  onChange: (v: string) => void;
  className?: string;
  placeholder?: string;
  maxLength?: number;
}) {
  return <input type="text" value={value ?? ""} maxLength={maxLength} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className={cn(INP, className)} />;
}

export function TimeInput({ value, onChange, className }: { value: string | null | undefined; onChange: (v: string | null) => void; className?: string }) {
  return <input type="time" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} className={cn(INP, "w-24", className)} />;
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex h-7 cursor-pointer items-center gap-1.5 text-[11px] text-text-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-3 accent-[var(--accent)]" />
      {label}
    </label>
  );
}

export function Section({ title, subtitle, children, actions }: { title: string; subtitle?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="border border-border bg-pane">
      <header className="flex h-9 items-center justify-between border-b border-border px-3">
        <div className="flex items-baseline gap-2">
          <h3 className="text-[12px] font-medium text-text-1">{title}</h3>
          {subtitle && <span className="text-[10px] text-text-3">{subtitle}</span>}
        </div>
        {actions}
      </header>
      <div className="flex flex-col gap-3 p-3">{children}</div>
    </section>
  );
}

export function Row({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("flex flex-wrap items-end gap-3", className)}>{children}</div>;
}
