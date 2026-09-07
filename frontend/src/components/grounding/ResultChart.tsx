"use client";

import { useMemo } from "react";

import type { ChartSpec } from "@/lib/types";

const SERIES_VARS = ["--accent", "--positive", "--caution"];

/** Dependency-free SVG bar / line chart for an analysis result. */
export function ResultChart({
  chart,
  columns,
  rows,
}: {
  chart: ChartSpec;
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
}) {
  const model = useMemo(() => {
    const xi = columns.indexOf(chart.x);
    const series = chart.series
      .map((name) => ({ name, i: columns.indexOf(name) }))
      .filter((s) => s.i >= 0);
    if (xi < 0 || !series.length) return null;

    const points = rows
      .map((r) => ({
        label: String(r[xi] ?? ""),
        values: series.map((s) => {
          const v = r[s.i];
          return typeof v === "number" ? v : Number(v) || 0;
        }),
      }))
      .filter((p) => p.label);
    if (points.length < 2) return null;

    const flat = points.flatMap((p) => p.values);
    const max = Math.max(0, ...flat);
    const min = Math.min(0, ...flat);
    return { series, points, max, min };
  }, [chart, columns, rows]);

  if (!model) return null;

  const W = 460;
  const H = 150;
  const padL = 40;
  const padB = 26;
  const padT = 8;
  const plotW = W - padL - 8;
  const plotH = H - padB - padT;
  const { series, points, max, min } = model;
  const range = max - min || 1;
  const y = (v: number) => padT + plotH - ((v - min) / range) * plotH;
  const zeroY = y(0);

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[150px] w-full min-w-[360px]" role="img">
        {/* baseline */}
        <line x1={padL} y1={zeroY} x2={W - 8} y2={zeroY} stroke="rgb(var(--line-strong))" strokeWidth="1" />
        {[max, min].map((v, k) => (
          <text key={k} x={padL - 6} y={y(v) + 3} textAnchor="end" className="fill-[rgb(var(--content-muted))] text-[9px]">
            {Number.isInteger(v) ? v.toLocaleString() : v.toFixed(0)}
          </text>
        ))}

        {chart.type === "line"
          ? series.map((s, si) => {
              const d = points
                .map((p, pi) => {
                  const cx = padL + (pi / (points.length - 1)) * plotW;
                  return `${pi === 0 ? "M" : "L"} ${cx.toFixed(1)} ${y(p.values[si]).toFixed(1)}`;
                })
                .join(" ");
              return (
                <path
                  key={s.name}
                  d={d}
                  fill="none"
                  stroke={`rgb(var(${SERIES_VARS[si % SERIES_VARS.length]}))`}
                  strokeWidth="2"
                />
              );
            })
          : points.map((p, pi) => {
              const groupW = plotW / points.length;
              const barW = Math.max(2, (groupW * 0.7) / series.length);
              return series.map((s, si) => {
                const v = p.values[si];
                const x = padL + pi * groupW + groupW * 0.15 + si * barW;
                const top = Math.min(y(v), zeroY);
                const h = Math.abs(y(v) - zeroY);
                return (
                  <rect
                    key={`${pi}-${si}`}
                    x={x}
                    y={top}
                    width={barW}
                    height={Math.max(1, h)}
                    rx="1"
                    fill={`rgb(var(${SERIES_VARS[si % SERIES_VARS.length]}))`}
                  />
                );
              });
            })}

        {points.map((p, pi) => {
          const cx =
            chart.type === "line"
              ? padL + (pi / (points.length - 1)) * plotW
              : padL + pi * (plotW / points.length) + plotW / points.length / 2;
          return (
            <text
              key={pi}
              x={cx}
              y={H - padB + 12}
              textAnchor="middle"
              className="fill-[rgb(var(--content-muted))] text-[9px]"
            >
              {p.label.length > 9 ? p.label.slice(0, 8) + "…" : p.label}
            </text>
          );
        })}
      </svg>
      {series.length > 1 && (
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 pl-10 text-[0.6rem] text-content-muted">
          {series.map((s, si) => (
            <span key={s.name} className="inline-flex items-center gap-1">
              <span
                className="h-2 w-2 rounded-[2px]"
                style={{ background: `rgb(var(${SERIES_VARS[si % SERIES_VARS.length]}))` }}
              />
              {s.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
