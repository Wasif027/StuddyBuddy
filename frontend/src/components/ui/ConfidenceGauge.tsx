"use client";

import type { ConfidenceLabel } from "@/lib/types";
import { cn } from "@/lib/utils";

const META: Record<ConfidenceLabel, { text: string; tone: string; blurb: string }> = {
  high: { text: "High confidence", tone: "text-positive", blurb: "Strong, well-cited evidence." },
  medium: { text: "Medium confidence", tone: "text-accent", blurb: "Reasonable support — verify specifics." },
  low: { text: "Low confidence", tone: "text-caution", blurb: "Thin evidence; treat with caution." },
  insufficient: {
    text: "Insufficient evidence",
    tone: "text-danger",
    blurb: "The knowledge base does not cover this.",
  },
};

function hue(pct: number) {
  return 12 + Math.max(0, Math.min(1, pct)) * 118;
}

export function ConfidenceBadge({
  value,
  label,
  size = "sm",
}: {
  value: number;
  label: ConfidenceLabel;
  size?: "sm" | "md";
}) {
  const m = META[label];
  return (
    <span
      className={cn("chip font-semibold", m.tone, size === "md" && "px-2.5 py-1 text-xs")}
      title={m.blurb}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {m.text}
      <span className="tnum opacity-70">{(value * 100).toFixed(0)}</span>
    </span>
  );
}

export function ConfidenceGauge({ value, label }: { value: number; label: ConfidenceLabel }) {
  const m = META[label];
  const pct = Math.max(0, Math.min(1, value));
  const r = 30;
  const circ = 2 * Math.PI * r;
  const gap = circ * 0.26; // three-quarter dial
  const track = circ - gap;

  return (
    <div className="flex items-center gap-3.5">
      <div className="relative h-[76px] w-[76px] shrink-0">
        <svg viewBox="0 0 76 76" className="h-full w-full" style={{ transform: "rotate(137deg)" }}>
          <circle
            cx="38"
            cy="38"
            r={r}
            fill="none"
            strokeWidth="6"
            strokeLinecap="round"
            className="stroke-surface-sunken"
            strokeDasharray={`${track} ${gap}`}
          />
          <circle
            cx="38"
            cy="38"
            r={r}
            fill="none"
            strokeWidth="6"
            strokeLinecap="round"
            stroke={`hsl(${hue(pct)} 52% 47%)`}
            strokeDasharray={`${track * pct} ${circ - track * pct}`}
            className="transition-[stroke-dasharray] duration-700 ease-spring"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="tnum text-lg font-semibold leading-none text-content-primary">
            {(pct * 100).toFixed(0)}
          </span>
          <span className="mt-1 text-[8px] uppercase tracking-[0.14em] text-content-muted">score</span>
        </div>
      </div>
      <div className="min-w-0">
        <p className={cn("text-[0.9rem] font-semibold tracking-tight", m.tone)}>{m.text}</p>
        <p className="mt-1 text-2xs leading-snug text-content-muted">{m.blurb}</p>
      </div>
    </div>
  );
}
