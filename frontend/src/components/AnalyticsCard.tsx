import type { LucideIcon } from "lucide-react";
import { cx } from "./ui";

const TONES = {
  brand: "bg-brand-50 text-brand-600",
  accent: "bg-accent-50 text-accent-600",
  warning: "bg-amber-50 text-amber-600",
  danger: "bg-red-50 text-red-600",
} as const;

/** Stat tile: label · value · optional hint. Values come from AnalyticsClient only. */
export function AnalyticsCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "brand",
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  hint?: string;
  tone?: keyof typeof TONES;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-card sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium leading-snug text-ink-soft">{label}</p>
        <span className={cx("grid h-9 w-9 flex-none place-items-center rounded-xl", TONES[tone])}>
          <Icon className="h-[18px] w-[18px]" aria-hidden />
        </span>
      </div>
      <p className="mt-3 text-3xl font-semibold tracking-tight text-ink" data-testid={`stat-${label}`}>
        {value.toLocaleString()}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}
