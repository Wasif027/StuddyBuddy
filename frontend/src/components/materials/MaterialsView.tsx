"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { DocumentRead, StudyGuideKind, StudyGuideResponse } from "@/lib/types";
import { cn, downloadBlob, formatRelativeTime } from "@/lib/utils";
import { toast } from "@/store/useToast";
import { useAppStore } from "@/store/useAppStore";
import { useUIStore } from "@/store/useUIStore";
import { AnswerText } from "@/components/chat/AnswerText";
import { MathText } from "@/components/ui/MathText";
import {
  ArrowLeft,
  Books,
  Cards,
  FileDoc,
  FilePdf,
  FilePpt,
  FileText,
  ImageIcon,
  Plus,
  Sparkle,
  Spinner,
  TextAlignLeft,
  Trash,
  TreeStructure,
  type Icon,
} from "@/components/ui/icons";

const KIND_ICON: Record<string, Icon> = {
  pdf: FilePdf,
  docx: FileDoc,
  pptx: FilePpt,
  image: ImageIcon,
};

const GUIDES: { kind: StudyGuideKind; label: string; icon: Icon }[] = [
  { kind: "guide", label: "Revision guide", icon: TextAlignLeft },
  { kind: "glossary", label: "Glossary", icon: Books },
  { kind: "cheatsheet", label: "Cheat sheet", icon: TextAlignLeft },
  { kind: "concept_map", label: "Concept map", icon: TreeStructure },
  { kind: "flashcards", label: "Flashcards", icon: Cards },
  { kind: "key_slides", label: "Key slides", icon: Sparkle },
];

export function MaterialsView() {
  const documents = useAppStore((s) => s.documents);
  const categories = useAppStore((s) => s.categories);
  const deleteDoc = useAppStore((s) => s.deleteDoc);
  const summariseDoc = useAppStore((s) => s.summariseDoc);
  const refreshMeta = useAppStore((s) => s.refreshMeta);
  const setIngestOpen = useUIStore((s) => s.setIngestOpen);
  const openDocumentId = useUIStore((s) => s.openDocumentId);
  const setOpenDocumentId = useUIStore((s) => s.setOpenDocumentId);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    refreshMeta();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (openDocumentId) {
      setOpenId(openDocumentId);
      setOpenDocumentId(null);
    }
  }, [openDocumentId, setOpenDocumentId]);

  const open = documents.find((d) => d.id === openId);
  if (open) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <button
          onClick={() => setOpenId(null)}
          className="btn btn-ghost mb-4 h-8 px-2 text-xs text-content-muted"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> All materials
        </button>
        <MaterialDetail doc={open} onSummarise={() => summariseDoc(open.id, open.title)} onDelete={() => {
          deleteDoc(open.id);
          setOpenId(null);
        }} />
      </div>
    );
  }

  const bySubject = new Map<string, DocumentRead[]>();
  for (const d of documents) {
    const key = d.category ?? "general";
    if (!bySubject.has(key)) bySubject.set(key, []);
    bySubject.get(key)!.push(d);
  }
  const label = (slug: string) =>
    categories.find((c) => c.slug === slug)?.label ?? slug.replace(/-/g, " ");

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-content-primary">Materials</h1>
        <button onClick={() => setIngestOpen(true)} className="btn btn-accent h-8 px-3 text-xs">
          <Plus className="h-3.5 w-3.5" /> Add
        </button>
      </div>
      <p className="mt-1 text-sm text-content-secondary">
        Your notes, slides and photos. Open one to build a study guide, or use them anywhere.
      </p>

      {documents.length === 0 ? (
        <button
          onClick={() => setIngestOpen(true)}
          className="mt-6 flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-line-strong px-4 py-12 text-center text-content-muted transition-colors hover:border-accent/60"
        >
          <Books className="h-7 w-7" />
          <span className="text-sm font-medium text-content-secondary">Nothing here yet</span>
          <span className="text-2xs">Upload a PDF, Word doc, slide deck, or a photo of a page</span>
        </button>
      ) : (
        <div className="mt-6 space-y-6">
          {[...bySubject.entries()].map(([slug, docs]) => (
            <div key={slug}>
              <h2 className="label mb-2">{label(slug)}</h2>
              <div className="space-y-1.5">
                {docs.map((d) => {
                  const KindIcon = KIND_ICON[d.sourceType] ?? FileText;
                  const kind = d.sourceType;
                  return (
                    <div
                      key={d.id}
                      className="group flex items-center gap-3 rounded-lg border border-line bg-surface-raised p-3 transition-colors hover:border-accent/40"
                    >
                      <KindIcon className="h-4 w-4 shrink-0 text-content-muted" />
                      <button onClick={() => setOpenId(d.id)} className="min-w-0 flex-1 text-left">
                        <p className="truncate text-sm font-medium text-content-primary">{d.title}</p>
                        <p className="text-2xs text-content-muted">
                          {kind}
                          {d.slideCount ? ` · ${d.slideCount} slides` : ""} ·{" "}
                          {d.status === "ready" ? formatRelativeTime(d.createdAt) : d.status}
                        </p>
                      </button>
                      <button
                        onClick={() => confirm(`Remove "${d.title}"?`) && deleteDoc(d.id)}
                        className="text-content-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                        aria-label="Delete"
                      >
                        <Trash className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MaterialDetail({
  doc,
  onSummarise,
  onDelete,
}: {
  doc: DocumentRead;
  onSummarise: () => void;
  onDelete: () => void;
}) {
  const [guide, setGuide] = useState<StudyGuideResponse | null>(null);
  const [loadingKind, setLoadingKind] = useState<StudyGuideKind | null>(null);

  const run = async (kind: StudyGuideKind) => {
    setLoadingKind(kind);
    setGuide(null);
    try {
      setGuide(await api.studyGuide(doc.id, kind));
    } catch (err) {
      toast.error("Couldn't build that", err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingKind(null);
    }
  };

  const isTimetable = doc.imageKind === "timetable";
  const guides = isTimetable ? [] : doc.slideCount ? GUIDES : GUIDES.filter((g) => g.kind !== "key_slides");

  return (
    <>
      <h2 className="text-lg font-semibold tracking-tight text-content-primary">{doc.title}</h2>
      <p className="mt-0.5 text-2xs text-content-muted">
        {doc.sourceType}
        {doc.slideCount ? ` · ${doc.slideCount} slides` : ""} · {doc.chunkCount} sections
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={onSummarise} className="btn h-8 px-3 text-xs">
          <Sparkle className="h-3.5 w-3.5" /> Ask the tutor about it
        </button>
        {guides.map((g) => (
          <button
            key={g.kind}
            onClick={() => run(g.kind)}
            disabled={loadingKind !== null}
            className="btn h-8 px-3 text-xs"
          >
            {loadingKind === g.kind ? (
              <Spinner className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <g.icon className="h-3.5 w-3.5" />
            )}
            {g.label}
          </button>
        ))}
        <button
          onClick={() => confirm(`Remove "${doc.title}"?`) && onDelete()}
          className="btn btn-ghost h-8 px-2 text-xs text-content-muted hover:text-danger"
        >
          <Trash className="h-3.5 w-3.5" /> Delete
        </button>
      </div>

      {guide && (
        <div className="card mt-5 p-5">
          <div className="mb-3 flex items-center justify-between">
            <p className="label">{guide.title}</p>
            <button
              onClick={async () => {
                try {
                  const blob = await api.exportMarkdown({
                    format: "pdf",
                    title: guide.title,
                    markdown: guideToMarkdown(guide),
                  });
                  downloadBlob(blob, "studybuddy-study-guide.pdf");
                } catch (err) {
                  toast.error("Couldn't make the PDF", err instanceof Error ? err.message : String(err));
                }
              }}
              className="btn btn-ghost h-7 px-2 text-2xs text-content-muted"
            >
              Download PDF
            </button>
          </div>
          {guide.markdown && <AnswerText text={guide.markdown} citations={[]} />}
          {guide.flashcards.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {guide.flashcards.map((c, i) => (
                <Flashcard key={i} front={c.front} back={c.back} hint={c.hint} />
              ))}
            </div>
          )}
          {guide.concepts.length > 0 && <ConceptTree nodes={guide.concepts} />}
          {guide.keySlides.length > 0 && (
            <div className="space-y-2">
              {guide.keySlides.map((s) => (
                <div key={s.index} className="rounded-lg border border-line p-3">
                  <p className="text-xs font-semibold text-content-primary">
                    Slide {s.index}
                    {s.title ? ` — ${s.title}` : ""}
                  </p>
                  {s.notes && <MathText text={s.notes} className="mt-1 block text-2xs text-content-secondary" />}
                  {s.bullets.length > 0 && (
                    <ul className="mt-1.5 list-disc pl-4 text-2xs text-content-muted">
                      {s.bullets.slice(0, 4).map((b, i) => (
                        <li key={i}><MathText text={b} /></li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function guideToMarkdown(g: StudyGuideResponse): string {
  if (g.markdown) return g.markdown;
  if (g.flashcards.length) {
    return g.flashcards.map((c, i) => `## ${i + 1}. ${c.front}\n\n${c.back}`).join("\n\n");
  }
  if (g.concepts.length) {
    return g.concepts.map((n) => `${"  ".repeat(0)}- **${n.label}**${n.note ? ` — ${n.note}` : ""}`).join("\n");
  }
  if (g.keySlides.length) {
    return g.keySlides
      .map((s) => `## Slide ${s.index}${s.title ? ` — ${s.title}` : ""}\n\n${s.notes ?? ""}\n\n${s.bullets.map((b) => `- ${b}`).join("\n")}`)
      .join("\n\n");
  }
  return "";
}

function Flashcard({ front, back, hint }: { front: string; back: string; hint: string | null }) {
  const [flipped, setFlipped] = useState(false);
  return (
    <button
      onClick={() => setFlipped((v) => !v)}
      className="min-h-[5rem] rounded-lg border border-line bg-surface-sunken p-3 text-left text-xs transition-colors hover:border-accent/40"
    >
      <MathText
        text={front}
        className={cn("font-medium", flipped ? "text-content-muted" : "text-content-primary")}
      />
      {flipped ? (
        <MathText text={back} className="mt-1.5 block text-content-secondary" />
      ) : (
        <p className="mt-1.5 text-2xs text-content-muted">
          {hint ? <MathText text={`Hint: ${hint}`} /> : "tap to flip"}
        </p>
      )}
    </button>
  );
}

function ConceptTree({ nodes }: { nodes: { id: string; label: string; parent: string | null; note: string | null }[] }) {
  const children = (pid: string | null) => nodes.filter((n) => (n.parent ?? null) === pid);
  const render = (pid: string | null, depth: number): React.ReactNode =>
    children(pid).map((n) => (
      <div key={n.id} style={{ marginLeft: depth * 14 }} className="border-l border-line pl-3">
        <MathText text={n.label} className="block text-xs font-medium text-content-primary" />
        {n.note && <MathText text={n.note} className="block text-2xs text-content-muted" />}
        {render(n.id, depth + 1)}
      </div>
    ));
  return <div className="space-y-1.5">{render(null, 0)}</div>;
}
