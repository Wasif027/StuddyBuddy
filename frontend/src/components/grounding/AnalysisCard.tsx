"use client";

import { useState } from "react";

import type { AnalysisBlock } from "@/lib/types";
import { copyToClipboard } from "@/lib/utils";
import { toast } from "@/store/useToast";
import { ChartBar, Check, Copy, Table, Warning } from "@/components/ui/icons";
import { DataTable } from "./DataTable";
import { ResultChart } from "./ResultChart";

export function AnalysisCard({ analysis }: { analysis: AnalysisBlock }) {
  const [showSql, setShowSql] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!analysis.ok) {
    return (
      <div className="rounded-lg border border-caution/30 bg-caution/8 p-3 text-2xs leading-relaxed text-caution">
        <p className="flex items-center gap-1.5 font-medium">
          <Warning className="h-3 w-3" weight="fill" /> Couldn&apos;t compute this
        </p>
        <p className="mt-1 text-content-secondary">
          {analysis.error || "The query could not be built from the spreadsheet."}
        </p>
        {analysis.assumptions && <p className="mt-1 text-content-muted">{analysis.assumptions}</p>}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-accent/25 bg-surface-raised">
      <div className="flex items-center gap-1.5 border-b border-line px-3 py-1.5 text-2xs font-semibold text-content-secondary">
        <ChartBar className="h-3 w-3 text-accent" weight="fill" />
        Computed result
        <span className="tnum ml-auto font-normal text-content-muted">
          {analysis.rowCount} row{analysis.rowCount === 1 ? "" : "s"}
          {analysis.truncated && " (capped)"}
        </span>
      </div>

      <div className="space-y-2.5 p-3">
        {analysis.chart && (
          <ResultChart chart={analysis.chart} columns={analysis.columns} rows={analysis.rows} />
        )}
        <DataTable columns={analysis.columns} rows={analysis.rows} />

        {analysis.assumptions && (
          <p className="text-[0.6rem] leading-snug text-content-muted">
            <span className="font-medium text-content-secondary">Assumptions: </span>
            {analysis.assumptions}
          </p>
        )}

        <div className="flex items-center gap-2 text-[0.6rem] text-content-muted">
          {analysis.tablesUsed.length > 0 && (
            <span className="inline-flex items-center gap-1">
              <Table className="h-3 w-3" /> {analysis.tablesUsed.join(", ")}
            </span>
          )}
          <button
            onClick={() => setShowSql((v) => !v)}
            className="ml-auto transition-colors hover:text-content-primary"
          >
            {showSql ? "Hide query" : "Show query"}
          </button>
        </div>

        {showSql && (
          <div className="relative">
            <pre className="overflow-x-auto rounded-md border border-line bg-surface-sunken p-2.5 text-[0.62rem] leading-relaxed text-content-secondary">
              <code className="font-mono">{analysis.sql}</code>
            </pre>
            <button
              onClick={async () => {
                if (await copyToClipboard(analysis.sql)) {
                  setCopied(true);
                  toast.success("Query copied");
                  setTimeout(() => setCopied(false), 1400);
                }
              }}
              className="absolute right-1.5 top-1.5 text-content-muted hover:text-content-primary"
              aria-label="Copy query"
            >
              {copied ? <Check className="h-3 w-3" weight="bold" /> : <Copy className="h-3 w-3" />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
