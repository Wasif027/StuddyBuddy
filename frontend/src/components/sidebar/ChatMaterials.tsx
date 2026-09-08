"use client";

import { useMemo, useState } from "react";

import { cn, formatRelativeTime } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useUIStore } from "@/store/useUIStore";
import {
  CaretDown,
  FileDoc,
  FilePdf,
  FilePpt,
  FileText,
  GitCompare,
  ImageIcon,
  Plus,
  Sparkle,
  type Icon,
} from "@/components/ui/icons";

const KIND_ICON: Record<string, Icon> = {
  pdf: FilePdf,
  docx: FileDoc,
  pptx: FilePpt,
  image: ImageIcon,
};

export function ChatMaterials() {
  const categories = useAppStore((s) => s.categories);
  const documents = useAppStore((s) => s.documents);
  const selectedCategoryId = useAppStore((s) => s.selectedCategoryId);
  const setCategory = useAppStore((s) => s.setCategory);
  const compareDocIds = useAppStore((s) => s.compareDocIds);
  const setCompareDocs = useAppStore((s) => s.setCompareDocs);
  const summariseDoc = useAppStore((s) => s.summariseDoc);
  const streaming = useAppStore((s) => s.streaming);
  const setIngestOpen = useUIStore((s) => s.setIngestOpen);

  const [open, setOpen] = useState(true);

  const withDocs = categories.filter((c) => c.docCount > 0);
  const visible = useMemo(
    () =>
      documents.filter((d) => !selectedCategoryId || d.category === selectedCategoryId),
    [documents, selectedCategoryId],
  );

  const toggleCompare = (id: string) =>
    setCompareDocs(
      compareDocIds.includes(id) ? compareDocIds.filter((x) => x !== id) : [...compareDocIds, id],
    );

  return (
    <div className="border-t border-line">
      <div className="flex items-center gap-1.5 px-3 py-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-1.5 text-[0.8rem] font-semibold tracking-tight text-content-primary"
        >
          <CaretDown className={cn("h-3 w-3 transition-transform", !open && "-rotate-90")} />
          Materials
          <span className="tnum ml-1 text-[0.6rem] font-normal text-content-muted">
            {documents.length}
          </span>
        </button>
        <button
          onClick={() => setIngestOpen(true)}
          className="text-content-muted hover:text-accent"
          aria-label="Add material"
        >
          <Plus className="h-3.5 w-3.5" weight="bold" />
        </button>
      </div>

      {open && (
        <div className="px-2 pb-2">
          {compareDocIds.length > 0 && (
            <div className="mb-2 flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent-soft px-2 py-1 text-2xs text-accent">
              <GitCompare className="h-3 w-3" weight="fill" />
              Comparing {compareDocIds.length}
              <button onClick={() => setCompareDocs([])} className="ml-auto opacity-70 hover:opacity-100">
                clear
              </button>
            </div>
          )}

          {withDocs.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              <Chip label="All" active={!selectedCategoryId} onClick={() => setCategory(null)} />
              {withDocs.map((c) => (
                <Chip
                  key={c.id}
                  label={c.label}
                  count={c.docCount}
                  active={c.slug === selectedCategoryId}
                  onClick={() => setCategory(c.slug === selectedCategoryId ? null : c.slug)}
                />
              ))}
            </div>
          )}

          <div className="max-h-56 space-y-0.5 overflow-y-auto">
            {visible.map((d) => {
              const selected = compareDocIds.includes(d.id);
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
                    title="Select to compare"
                    className="h-3 w-3 shrink-0 accent-[rgb(var(--accent))]"
                  />
                  <KindIcon className="h-3.5 w-3.5 shrink-0 text-content-muted" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-content-secondary">{d.title}</p>
                    <p className="tnum text-[0.6rem] text-content-muted">
                      {ready
                        ? `${d.slideCount ? `${d.slideCount} slides · ` : ""}${formatRelativeTime(d.createdAt)}`
                        : d.status === "failed"
                          ? d.error ?? "couldn't be read"
                          : d.status}
                    </p>
                  </div>
                  {ready && (
                    <button
                      onClick={() => summariseDoc(d.id, d.title)}
                      disabled={streaming}
                      className="text-content-muted opacity-0 transition-opacity hover:text-accent disabled:cursor-not-allowed group-hover:opacity-100"
                      title="Study summary"
                    >
                      <Sparkle className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              );
            })}
            {documents.length === 0 && (
              <button
                onClick={() => setIngestOpen(true)}
                className="w-full rounded-md border border-dashed border-line px-2 py-3 text-2xs text-content-muted hover:border-accent/50 hover:text-content-primary"
              >
                Upload your notes, slides or a photo →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Chip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
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
      {label}
      {count != null && <span className="tnum opacity-60">{count}</span>}
    </button>
  );
}
