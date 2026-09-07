"use client";

import { useState } from "react";

import { useAppStore } from "@/store/useAppStore";
import { ArrowRight, GitCompare, Plus, Quotes, ShieldCheck, Stack } from "@/components/ui/icons";
import { IngestDialog } from "@/components/sidebar/IngestDialog";

export function EmptyState() {
  const documents = useAppStore((s) => s.documents);
  const categories = useAppStore((s) => s.categories);
  const ask = useAppStore((s) => s.ask);
  const loadingMeta = useAppStore((s) => s.loadingMeta);
  const health = useAppStore((s) => s.health);
  const [ingestOpen, setIngestOpen] = useState(false);

  const hasDocs = documents.length > 0;

  // Starters derived from what's actually uploaded, not canned questions.
  const hasSheet = documents.some((d) => d.sourceType === "xlsx" || d.sourceType === "xls");
  const starters = [
    ...categories
      .map((c) => c.label)
      .filter(Boolean)
      .slice(0, 2)
      .map((l) => `Summarise the ${l} documents.`),
    hasSheet ? "What stands out in the spreadsheet data — any figures I should worry about?" : null,
    documents.length >= 2 ? "What are the key differences between my documents?" : null,
    "What questions can these documents answer?",
  ]
    .filter((q): q is string => Boolean(q))
    .slice(0, 4);

  return (
    <div className="mx-auto w-full max-w-[42rem] px-5 py-14">
      <div className="stagger">
        <h1 className="text-[2rem] font-semibold leading-[1.1] tracking-[-0.03em] text-content-primary">
          {hasDocs ? (
            <>
              Ask your
              <br />
              knowledge base.
            </>
          ) : (
            <>Add a document to get started.</>
          )}
        </h1>

        {hasDocs ? (
          <>
            <p className="mt-4 max-w-[46ch] text-[0.95rem] leading-relaxed text-content-secondary">
              Every answer is grounded in your {documents.length} document
              {documents.length === 1 ? "" : "s"} and returns inline citations, a confidence score, the
              source passages, and suggested next steps.
            </p>
            <div className="mt-8 flex flex-col divide-y divide-line border-y border-line">
              {starters.map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q, {})}
                  className="group flex items-center gap-4 py-3.5 text-left transition-colors hover:bg-surface-sunken/60"
                >
                  <Quotes className="h-4 w-4 shrink-0 text-content-muted transition-colors group-hover:text-accent" />
                  <span className="flex-1 text-[0.9rem] leading-snug text-content-secondary transition-colors group-hover:text-content-primary">
                    {q}
                  </span>
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 -translate-x-1 text-content-muted opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
                </button>
              ))}
            </div>
            <div className="mt-6 flex flex-wrap gap-x-5 gap-y-1.5 text-2xs text-content-muted">
              <span className="inline-flex items-center gap-1.5">
                <Stack className="h-3 w-3" /> hybrid retrieval · vector + keyword + rerank
              </span>
              <span className="inline-flex items-center gap-1.5">
                <GitCompare className="h-3 w-3" /> tick 2+ documents to compare them
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-3 w-3" />
                {health?.llmActive
                  ? `${health.llmProvider} · ${health.llmModel}`
                  : "offline extractive mode"}
              </span>
            </div>
          </>
        ) : (
          <>
            <p className="mt-4 max-w-[46ch] text-[0.95rem] leading-relaxed text-content-secondary">
              Add your policies, contracts, spreadsheets, decks or notes — then ask questions and
              get answers with citations, run calculations over your data, and get suggested next
              steps.
            </p>
            {!loadingMeta && (
              <button onClick={() => setIngestOpen(true)} className="btn btn-accent mt-7 px-4 py-2.5">
                <Plus className="h-4 w-4" weight="bold" /> Add your first document
              </button>
            )}
          </>
        )}
      </div>
      <IngestDialog open={ingestOpen} onClose={() => setIngestOpen(false)} />
    </div>
  );
}
