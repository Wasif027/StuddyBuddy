"use client";

import { cn } from "@/lib/utils";

/** Thin 0–1 meter. Fill hue tracks the value (clay → ochre → pine). */
export function ScoreBar({
  score,
  label,
  sublabel,
  height = 4,
  className,
}: {
  score: number;
  label?: string;
  sublabel?: string;
  height?: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const hue = 12 + (pct / 100) * 118; // 12° clay → 130° pine

  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      {label && (
        <span className="w-16 shrink-0 truncate text-2xs font-medium tracking-tight text-content-muted">
          {label}
        </span>
      )}
      <div
        className="relative flex-1 overflow-hidden rounded-full bg-surface-sunken ring-1 ring-inset ring-line/60"
        style={{ height }}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ease-spring"
          style={{ width: `${pct}%`, background: `hsl(${hue} 52% 46%)` }}
        />
      </div>
      <span className="tnum w-9 shrink-0 text-right text-2xs text-content-muted">
        {sublabel ?? `${pct.toFixed(0)}%`}
      </span>
    </div>
  );
}
