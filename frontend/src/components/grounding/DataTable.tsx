"use client";

import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";

type Cell = string | number | boolean | null;

const isNum = (v: Cell): v is number => typeof v === "number";

function fmt(v: Cell): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}

/** Compact, scrollable result table. Numeric columns right-align with tabular figures. */
export function DataTable({
  columns,
  rows,
  maxRows = 12,
  className,
}: {
  columns: string[];
  rows: Cell[][];
  maxRows?: number;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const numericCol = useMemo(
    () => columns.map((_, ci) => rows.length > 0 && rows.every((r) => r[ci] === null || isNum(r[ci]))),
    [columns, rows],
  );
  const shown = expanded ? rows : rows.slice(0, maxRows);

  if (!columns.length) return null;

  return (
    <div className={cn("overflow-hidden rounded-lg border border-line", className)}>
      <div className="max-h-[22rem] overflow-auto">
        <table className="w-full border-collapse text-2xs">
          <thead className="sticky top-0 z-10 bg-surface-sunken">
            <tr>
              {columns.map((c, ci) => (
                <th
                  key={ci}
                  className={cn(
                    "whitespace-nowrap border-b border-line px-2.5 py-1.5 font-semibold text-content-secondary",
                    numericCol[ci] ? "text-right" : "text-left",
                  )}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, ri) => (
              <tr key={ri} className="even:bg-surface-sunken/40">
                {columns.map((_, ci) => (
                  <td
                    key={ci}
                    className={cn(
                      "whitespace-nowrap px-2.5 py-1 text-content-primary",
                      numericCol[ci] ? "tnum text-right" : "text-left",
                    )}
                  >
                    {fmt(r[ci] ?? null)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > maxRows && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full border-t border-line bg-surface-sunken/50 py-1 text-[0.6rem] text-content-muted hover:text-content-primary"
        >
          {expanded ? "Show fewer" : `Show all ${rows.length} rows`}
        </button>
      )}
    </div>
  );
}
