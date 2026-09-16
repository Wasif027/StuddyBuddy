"use client";

import type { ChartSpec } from "@/lib/types";

/**
 * Dependency-light SVG renderer for a tutor-generated chart (line / scatter /
 * bar) — the model computes real data points, this just draws them. No
 * charting library: consistent with the hand-rolled Sparkline in ProgressView.
 */

const PALETTE = ["--accent", "--positive", "--danger", "--caution"];
const seriesColor = (i: number) => `rgb(var(${PALETTE[i % PALETTE.length]}))`;

const W = 560;
const H = 300;
const PAD = { top: 28, right: 20, bottom: 40, left: 48 };

function niceTicks(min: number, max: number, count = 5): number[] {
  if (min === max) return [min];
  const span = max - min;
  const step = span / (count - 1);
  return Array.from({ length: count }, (_, i) => min + i * step);
}

export function ChartView({ chart }: { chart: ChartSpec }) {
  const allPoints = chart.series.flatMap((s) => s.points);
  if (allPoints.length === 0) return null;

  const xs = allPoints.map((p) => p.x);
  const ys = allPoints.map((p) => p.y);
  let xMin = Math.min(...xs);
  let xMax = Math.max(...xs);
  let yMin = Math.min(0, ...ys);
  let yMax = Math.max(...ys);
  if (xMin === xMax) { xMin -= 1; xMax += 1; }
  if (yMin === yMax) { yMin -= 1; yMax += 1; }
  const yPad = (yMax - yMin) * 0.08;
  yMin -= yPad;
  yMax += yPad;

  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const sx = (x: number) => PAD.left + ((x - xMin) / (xMax - xMin)) * plotW;
  const sy = (y: number) => PAD.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

  const yTicks = niceTicks(yMin, yMax, 5);
  const xTicks = niceTicks(xMin, xMax, Math.min(6, Math.max(2, allPoints.length)));
  const fmt = (n: number) => (Math.abs(n) >= 1000 || (Math.abs(n) < 0.01 && n !== 0) ? n.toExponential(1) : Number(n.toFixed(2)).toString());

  const barW = chart.type === "bar" ? plotW / (allPoints.length * chart.series.length + 1) : 0;

  return (
    <figure className="my-2 overflow-x-auto rounded-lg border border-line bg-surface-raised p-3">
      {chart.title && <figcaption className="mb-1 text-xs font-medium text-content-secondary">{chart.title}</figcaption>}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 420 }} role="img" aria-label={chart.title || "chart"}>
        {/* gridlines + y ticks */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(t)} y2={sy(t)} stroke="rgb(var(--line))" strokeWidth={1} />
            <text x={PAD.left - 6} y={sy(t)} textAnchor="end" dominantBaseline="middle" fontSize={9} fill="rgb(var(--content-muted))">
              {fmt(t)}
            </text>
          </g>
        ))}
        {/* x ticks */}
        {xTicks.map((t, i) => (
          <text key={i} x={sx(t)} y={H - PAD.bottom + 16} textAnchor="middle" fontSize={9} fill="rgb(var(--content-muted))">
            {fmt(t)}
          </text>
        ))}
        {/* axes */}
        <line x1={PAD.left} x2={PAD.left} y1={PAD.top} y2={H - PAD.bottom} stroke="rgb(var(--content-muted))" strokeWidth={1} />
        <line x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} stroke="rgb(var(--content-muted))" strokeWidth={1} />

        {chart.type === "bar"
          ? chart.series.map((s, si) => (
              <g key={si}>
                {s.points.map((p, pi) => {
                  const x = PAD.left + (pi * chart.series.length + si) * barW * 1.15 + barW * 0.3;
                  const y0 = sy(Math.min(0, p.y));
                  const y1 = sy(Math.max(0, p.y));
                  return (
                    <rect key={pi} x={x} y={y1} width={Math.max(2, barW * 0.8)} height={Math.max(0.5, y0 - y1)}
                      fill={seriesColor(si)} opacity={0.85} />
                  );
                })}
              </g>
            ))
          : chart.series.map((s, si) => {
              const color = seriesColor(si);
              const sorted = [...s.points].sort((a, b) => a.x - b.x);
              const d = sorted.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`).join(" ");
              return (
                <g key={si}>
                  {chart.type === "line" && <path d={d} fill="none" stroke={color} strokeWidth={1.75} />}
                  {sorted.map((p, i) => (
                    <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={chart.type === "scatter" ? 2.75 : 2} fill={color} />
                  ))}
                </g>
              );
            })}

        {chart.xLabel && (
          <text x={PAD.left + plotW / 2} y={H - 4} textAnchor="middle" fontSize={10} fill="rgb(var(--content-muted))">
            {chart.xLabel}
          </text>
        )}
        {chart.yLabel && (
          <text x={12} y={PAD.top + plotH / 2} textAnchor="middle" fontSize={10} fill="rgb(var(--content-muted))"
            transform={`rotate(-90 12 ${PAD.top + plotH / 2})`}>
            {chart.yLabel}
          </text>
        )}
      </svg>
      {chart.series.length > 1 && (
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-2xs text-content-muted">
          {chart.series.map((s, si) => (
            <span key={si} className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: seriesColor(si) }} />
              {s.name || `Series ${si + 1}`}
            </span>
          ))}
        </div>
      )}
    </figure>
  );
}
