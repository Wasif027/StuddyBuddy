"use client";

import { useMemo, useState } from "react";

import type { DocStatus } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import {
  CaretDown,
  ChartBar,
  FileDoc,
  FilePdf,
  FilePpt,
  FileText,
  FileXls,
  GitCompare,
  Plus,
  Refresh,
  Sparkle,
  Trash,
  type Icon,
} from "@/components/ui/icons";
import { IngestDialog } from "./IngestDialog";

const KIND_ICON: Record<string, Icon> = {
  pdf: FilePdf,
  docx: FileDoc,
  xlsx: FileXls,
  xls: FileXls,
  pptx: FilePpt,
};

const STATUS_TONE: Record<DocStatus, string> = {
  ready: "bg-positive",
  processing: "bg-accent",
  indexing: "bg-caution",
  failed: "bg-danger",
  empty: "bg-content-muted",
};

export function KnowledgeBase() {
  const categories = useAppStore((s) => s.categories);
  const documents = useAppStore((s) => s.documents);
  const selectedCategoryId = useAppStore((s) => s.selectedCategoryId);
  const setCategory = useAppStore((s) => s.setCategory);
  const compareDocIds = useAppStore((s) => s.compareDocIds);
  const setCompareDocs = useAppStore((s) => s.setCompareDocs);
  const deleteDoc = useAppStore((s) => s.deleteDoc);
  const summariseDoc = useAppStore((s) => s.summariseDoc);
  const analyseDoc = useAppStore((s) => s.analyseDoc);
  const streaming = useAppStore((s) => s.streaming);
  const refreshMeta = useAppStore((s) => s.refreshMeta);
  const loadingMeta = useAppStore((s) => s.loadingMeta);

  const [open, setOpen] = useState(true);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const totalDocs = documents.length;
  const totalChunks = categories.reduce((a, c) => a + c.chunkCount, 0);

  const visibleDocs = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return documents.filter(
      (d) =>
        (!selectedCategoryId || d.category === selectedCategoryId) &&
        (!q || d.title.toLowerCase().includes(q)),
    );
  }, [documents, selectedCategoryId, filter]);

  const toggleCompare = (id: string) => {
    const next = compareDocIds.includes(id)
      ? compareDocIds.filter((x) => x !== id)
      : [...compareDocIds, id];
    setCompareDocs(next);
  };

  return (
    <div className="border-t border-line">
      <div className="flex items-center gap-1.5 px-3 py-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-1.5 text-[0.8rem] font-semibold tracking-tight text-content-primary"
        >
          <CaretDown className={cn("h-3 w-3 transition-transform", !open && "-rotate-90")} />
          Knowledge base
          <span className="tnum ml-1 text-[0.6rem] font-normal text-content-muted">
            {totalDocs} · {totalChunks} sections
          </span>
        </button>
        <button
          onClick={refreshMeta}
          className="text-content-muted hover:text-content-primary"
          aria-label="Refresh"
        >
          <Refresh className={cn("h-3.5 w-3.5", loadingMeta && "animate-spin")} />
        </button>
      </div>

      {open && (
        <div className="px-2 pb-2">
          <button onClick={() => setIngestOpen(true)} className="btn w-full py-1.5 text-xs">
            <Plus className="h-3.5 w-3.5" weight="bold" /> Add document
          </button>

          {compareDocIds.length > 0 && (
            <div className="mt-2 flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent-soft px-2 py-1 text-2xs text-accent">
              <GitCompare className="h-3 w-3" weight="fill" />
              Compare mode · {compareDocIds.length} selected
              <button onClick={() => setCompareDocs([])} className="ml-auto opacity-70 hover:opacity-100">
                clear
              </button>
            </div>
          )}

          {categories.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              <ScopeChip label="All" active={!selectedCategoryId} onClick={() => setCategory(null)} />
              {categories.map((c) => (
                <ScopeChip
                  key={c.id}
                  label={c.label}
                  dot={STATUS_TONE[c.status]}
                  count={c.docCount}
                  active={c.id === selectedCategoryId}
                  onClick={() => setCategory(c.id === selectedCategoryId ? null : c.id)}
                />
              ))}
            </div>
          )}

          {documents.length > 6 && (
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="filter documents"
              className="mt-2 w-full rounded-md border border-line bg-surface-base px-2 py-1 text-2xs focus:border-accent/50 focus:outline-none"
            />
          )}

          <div className="mt-1.5 max-h-64 space-y-0.5 overflow-y-auto">
            {visibleDocs.map((d) => {
              const selected = compareDocIds.includes(d.id);
              const isSheet = d.sourceType === "xlsx" || d.sourceType === "xls";
              const KindIcon = KIND_ICON[d.sourceType] ?? FileText;
              const ready = d.status === "ready";
              return (
                <div
                  key={d.id}
                  className={cn(
                    "group flex items-center gap-2 rounded-md px-1.5 py-1.5 transition-colors",
                    selected ? "bg-accent-soft" : "hover:bg-surface-sunken",
                    d.status === "failed" && "opacity-60",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => toggleCompare(d.id)}
                    title="Select for compare mode"
                    className="h-3 w-3 shrink-0 accent-[rgb(var(--accent))]"
                  />
                  <KindIcon className="h-3.5 w-3.5 shrink-0 text-content-muted" />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 truncate text-xs font-medium text-content-secondary">
                      {!ready && (
                        <span
                          className={cn(
                            "h-1.5 w-1.5 shrink-0 rounded-full",
                            STATUS_TONE[d.status as DocStatus] ?? "bg-content-muted",
                          )}
                          title={d.error ?? d.status}
                        />
                      )}
                      <span className="truncate">{d.title}</span>
                    </p>
                    <p className="tnum text-[0.6rem] text-content-muted">
                      {ready
                        ? `${d.chunkCount} sections · ${formatRelativeTime(d.createdAt)}`
                        : d.status === "failed"
                          ? "couldn't be read — hover the dot"
                          : d.status}
                    </p>
                  </div>
                  {ready &&
                    (isSheet ? (
                      <button
                        onClick={() => analyseDoc(d.id, d.title)}
                        disabled={streaming}
                        className="text-content-muted opacity-0 transition-opacity hover:text-accent disabled:cursor-not-allowed group-hover:opacity-100"
                        aria-label={`Analyse ${d.title}`}
                        title="Analyse this data"
                      >
                        <ChartBar className="h-3.5 w-3.5" />
                      </button>
                    ) : (
                      <button
                        onClick={() => summariseDoc(d.id, d.title)}
                        disabled={streaming}
                        className="text-content-muted opacity-0 transition-opacity hover:text-accent disabled:cursor-not-allowed group-hover:opacity-100"
                        aria-label={`Summarise ${d.title}`}
                        title="Summarise this document"
                      >
                        <Sparkle className="h-3.5 w-3.5" />
                      </button>
                    ))}
                  <button
                    onClick={() => confirm(`Remove "${d.title}"?`) && deleteDoc(d.id)}
                    className="text-content-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                    aria-label={`Delete ${d.title}`}
                  >
                    <Trash className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
            {loadingMeta && documents.length === 0 && (
              <div className="space-y-1 px-1 py-1">
                <div className="skeleton h-3 w-3/4" />
                <div className="skeleton h-3 w-1/2" />
              </div>
            )}
            {!loadingMeta && documents.length === 0 && (
              <p className="px-1.5 py-2 text-2xs text-content-muted">
                No documents yet. Add one to start asking questions.
              </p>
            )}
          </div>
          <p className="mt-1 px-1.5 text-[0.58rem] leading-tight text-content-muted">
            Hover a document for <Sparkle className="inline h-2.5 w-2.5" /> summarise. Tick 2+ to
            compare them in a question.
          </p>
        </div>
      )}

      <IngestDialog open={ingestOpen} onClose={() => setIngestOpen(false)} />
    </div>
  );
}

function ScopeChip({
  label,
  dot,
  count,
  active,
  onClick,
}: {
  label: string;
  dot?: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[0.65rem] font-medium transition-colors",
        active
          ? "border-accent/40 bg-accent-soft text-accent"
          : "border-line bg-surface-sunken text-content-muted hover:text-content-primary",
      )}
    >
      {dot && <span className={cn("h-1 w-1 rounded-full", dot)} />}
      {label}
      {count != null && <span className="tnum opacity-60">{count}</span>}
    </button>
  );
}
