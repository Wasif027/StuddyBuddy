"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { NoteKind, NoteRead, RoutineDay } from "@/lib/types";
import { cn, downloadBlob, formatRelativeTime } from "@/lib/utils";
import { toast } from "@/store/useToast";
import { useStudyStore } from "@/store/useStudyStore";
import { useUIStore } from "@/store/useUIStore";
import { useIsMobile } from "@/lib/useIsMobile";
import { AnswerText } from "@/components/chat/AnswerText";
import {
  ArrowLeft,
  Books,
  CalendarBlank,
  Exam,
  NotePencil,
  Plus,
  PushPin,
  Spinner,
  Trash,
  UploadSimple,
} from "@/components/ui/icons";

const KIND_LABEL: Record<NoteKind, string> = {
  note: "Note",
  log: "Learning log",
  routine: "Timetable",
  saved: "From chat",
};

const FILTERS: { id: NoteKind | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "note", label: "Notes" },
  { id: "log", label: "Log" },
  { id: "saved", label: "Saved" },
  { id: "routine", label: "Timetables" },
];

export function NotesView() {
  const notes = useStudyStore((s) => s.notes);
  const loading = useStudyStore((s) => s.loadingNotes);
  const load = useStudyStore((s) => s.loadNotes);
  const create = useStudyStore((s) => s.createNote);
  const remove = useStudyStore((s) => s.deleteNote);
  const isMobile = useIsMobile();
  const [filter, setFilter] = useState<NoteKind | "all">("all");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draftKind, setDraftKind] = useState<"note" | "log">("note");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");

  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const visible = useMemo(
    () =>
      notes.filter(
        (n) =>
          (filter === "all" || n.kind === filter) &&
          (!q || (n.title + n.bodyMd).toLowerCase().includes(q.toLowerCase())),
      ),
    [notes, filter, q],
  );
  const selected = notes.find((n) => n.id === selectedId) ?? null;

  const todayLabel = () =>
    new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

  const startCreating = (kind: "note" | "log") => {
    setDraftKind(kind);
    setDraftTitle(kind === "log" ? `Learning log — ${todayLabel()}` : "");
    setDraftBody("");
    setCreating(true);
  };

  const addNote = async () => {
    if (!draftTitle.trim()) return;
    await create({
      title: draftTitle.trim(),
      kind: draftKind,
      bodyMd: draftBody.trim() || undefined,
    });
    setDraftTitle("");
    setDraftBody("");
    setCreating(false);
  };

  const cancelCreating = () => {
    setDraftTitle("");
    setDraftBody("");
    setCreating(false);
  };

  // Phones get a single full-width pane that swaps between the list and the
  // open note (with a back button), instead of the desktop two-column split.
  if (isMobile && selected) {
    return (
      <div className="mx-auto w-full max-w-3xl px-5 py-8">
        <button
          onClick={() => setSelectedId(null)}
          className="btn btn-ghost mb-4 h-8 px-2 text-xs text-content-muted"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> All notes
        </button>
        <NoteDetail note={selected} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-5xl gap-5 px-5 py-8">
      <div className={cn(isMobile ? "w-full" : "w-72 shrink-0")}>
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight text-content-primary">Notes</h1>
          <div className="flex items-center gap-1">
            <button
              onClick={() => (creating && draftKind === "log" ? setCreating(false) : startCreating("log"))}
              className="btn btn-ghost h-7 w-7 !p-0 text-content-muted"
              aria-label="New learning log entry"
              title="Log what you learned today"
            >
              <CalendarBlank className="h-4 w-4" weight="bold" />
            </button>
            <button
              onClick={() => (creating && draftKind === "note" ? setCreating(false) : startCreating("note"))}
              className="btn btn-ghost h-7 w-7 !p-0 text-content-muted"
              aria-label="New note"
            >
              <Plus className="h-4 w-4" weight="bold" />
            </button>
          </div>
        </div>

        {creating && (
          <div className="mt-2 space-y-1.5">
            <div className="flex gap-1">
              <input
                autoFocus
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && draftKind === "note") addNote();
                  if (e.key === "Escape") cancelCreating();
                }}
                placeholder={draftKind === "log" ? "Log title" : "Note title"}
                className="input py-1.5 text-xs"
              />
              {draftKind === "note" && (
                <>
                  <button onClick={addNote} className="btn btn-accent h-8 px-2 text-xs">
                    Add
                  </button>
                  <button onClick={cancelCreating} className="btn btn-ghost h-8 px-2 text-xs text-content-muted">
                    Cancel
                  </button>
                </>
              )}
            </div>
            {draftKind === "log" && (
              <>
                <textarea
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                  onKeyDown={(e) => e.key === "Escape" && cancelCreating()}
                  rows={4}
                  placeholder="What did you learn today?"
                  className="input py-1.5 text-xs leading-relaxed"
                />
                <div className="flex gap-1">
                  <button onClick={addNote} className="btn btn-accent h-8 flex-1 text-xs">
                    Add to log
                  </button>
                  <button onClick={cancelCreating} className="btn btn-ghost h-8 px-3 text-xs text-content-muted">
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search notes"
          className="input mt-3 py-1.5 text-xs"
        />

        <div className="mt-2 flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-md border px-1.5 py-0.5 text-[0.65rem] font-medium transition-colors",
                filter === f.id
                  ? "border-accent/40 bg-accent-soft text-accent"
                  : "border-line bg-surface-sunken text-content-muted hover:text-content-primary",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="mt-3 space-y-1">
          {loading && <div className="skeleton h-12" />}
          {!loading && visible.length === 0 && (
            <p className="px-1 py-3 text-2xs text-content-muted">
              No notes yet. Ask the tutor something and hit “Save”, upload a photo of your notes, or
              add one here.
            </p>
          )}
          {visible.map((n) => (
            <div
              key={n.id}
              className={cn(
                "group flex items-center gap-1 rounded-md transition-colors",
                selectedId === n.id ? "bg-accent-soft" : "hover:bg-surface-sunken",
              )}
            >
              <button
                onClick={() => setSelectedId(n.id)}
                className="flex min-w-0 flex-1 flex-col gap-0.5 px-2.5 py-2 text-left"
              >
                <span className="flex items-center gap-1.5">
                  {n.pinned && <PushPin className="h-3 w-3 text-accent" weight="fill" />}
                  <span
                    className={cn(
                      "truncate text-xs font-medium",
                      selectedId === n.id ? "text-accent" : "text-content-secondary",
                    )}
                  >
                    {n.title}
                  </span>
                </span>
                <span className="text-[0.6rem] text-content-muted">
                  {KIND_LABEL[n.kind]} · {formatRelativeTime(n.updatedAt)}
                </span>
              </button>
              <button
                onClick={() => {
                  if (!confirm(`Delete "${n.title}"?`)) return;
                  remove(n.id);
                  if (selectedId === n.id) setSelectedId(null);
                }}
                className="mr-1.5 shrink-0 rounded p-1 text-content-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                aria-label={`Delete ${n.title}`}
              >
                <Trash className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {!isMobile && (
        <div className="min-w-0 flex-1">
          {selected ? (
            <NoteDetail note={selected} />
          ) : (
            <div className="grid h-full place-items-center text-center text-sm text-content-muted">
              <div>
                <NotePencil className="mx-auto h-6 w-6 opacity-50" />
                <p className="mt-2">Pick a note to read it.</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function NoteDetail({ note }: { note: NoteRead }) {
  const update = useStudyStore((s) => s.updateNote);
  const del = useStudyStore((s) => s.deleteNote);
  const quiz = useStudyStore((s) => s.quizFromNote);
  const generating = useStudyStore((s) => s.generating);
  const uploadInto = useStudyStore((s) => s.uploadIntoNote);
  const setView = useUIStore((s) => s.setView);
  const setOpenDocumentId = useUIStore((s) => s.setOpenDocumentId);
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(note.bodyMd);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setBody(note.bodyMd);
    setEditing(false);
  }, [note.id, note.bodyMd]);

  const days = (note.structured?.days as RoutineDay[] | undefined) ?? [];
  const linkedMaterial = (note.source === "image" || note.source === "upload") && note.sourceRef;

  const handleFile = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    await uploadInto(note.id, file);
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <article className="card p-5">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold tracking-tight text-content-primary">{note.title}</h2>
          <p className="mt-0.5 text-2xs text-content-muted">
            {KIND_LABEL[note.kind]}
            {note.category ? ` · ${note.category}` : ""} · {formatRelativeTime(note.updatedAt)}
          </p>
        </div>
        <button
          onClick={() => update(note.id, { pinned: !note.pinned })}
          className={cn("rounded p-1", note.pinned ? "text-accent" : "text-content-muted hover:text-content-primary")}
          aria-label="Pin"
        >
          <PushPin className="h-4 w-4" weight={note.pinned ? "fill" : "regular"} />
        </button>
        <button
          onClick={() => confirm("Delete this note?") && del(note.id)}
          className="rounded p-1 text-content-muted hover:text-danger"
          aria-label="Delete"
        >
          <Trash className="h-4 w-4" />
        </button>
      </div>

      {note.kind === "routine" && days.length > 0 && (
        <div className="mt-4 space-y-2">
          {days.map((d) => (
            <div key={d.day} className="rounded-lg border border-line p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-content-primary">
                <CalendarBlank className="h-3.5 w-3.5 text-accent" /> {d.day}
              </p>
              <div className="mt-1.5 space-y-1">
                {d.entries.map((e, i) => (
                  <p key={i} className="flex gap-2 text-xs text-content-secondary">
                    <span className="tnum w-14 shrink-0 text-content-muted">{e.time ?? ""}</span>
                    <span className="font-medium">{e.label}</span>
                    {e.location && <span className="text-content-muted">· {e.location}</span>}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 border-t border-line pt-4">
        {editing ? (
          <>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={14}
              className="input font-mono text-2xs leading-relaxed"
            />
            <div className="mt-2 flex gap-2">
              <button
                onClick={async () => {
                  setSaving(true);
                  await update(note.id, { bodyMd: body });
                  setSaving(false);
                  setEditing(false);
                }}
                disabled={saving}
                className="btn btn-accent h-8 px-3 text-xs"
              >
                {saving && <Spinner className="h-3.5 w-3.5 animate-spin" />}
                Save
              </button>
              <button onClick={() => setEditing(false)} disabled={saving} className="btn h-8 px-3 text-xs">
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <AnswerText text={note.bodyMd || "_(empty)_"} citations={[]} />
            <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
              <button onClick={() => setEditing(true)} className="btn h-8 px-3 text-xs">
                <NotePencil className="h-3.5 w-3.5" /> Edit
              </button>
              {note.kind !== "routine" && (
                <button
                  onClick={() => quiz(note.id)}
                  disabled={generating}
                  className="btn h-8 px-3 text-xs"
                >
                  {generating ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Exam className="h-3.5 w-3.5" />}
                  Quiz me on this
                </button>
              )}
              <button
                onClick={async () => {
                  try {
                    const blob = await api.exportMarkdown({
                      format: "pdf",
                      title: note.title,
                      markdown: note.bodyMd,
                    });
                    downloadBlob(blob, "studybuddy-note.pdf");
                  } catch (err) {
                    toast.error("Couldn't make the PDF", err instanceof Error ? err.message : String(err));
                  }
                }}
                className="btn h-8 px-3 text-xs"
              >
                Download PDF
              </button>
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="btn h-8 px-3 text-xs"
                title="Upload a PDF, Word doc, slide deck, or photo — its text fills in this note"
              >
                {uploading ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <UploadSimple className="h-3.5 w-3.5" />}
                {uploading ? "Reading…" : "Upload a file"}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
              />
              {linkedMaterial && (
                <button
                  onClick={() => {
                    setOpenDocumentId(note.sourceRef);
                    setView("materials");
                  }}
                  className="btn h-8 px-3 text-xs"
                >
                  <Books className="h-3.5 w-3.5" /> View uploaded material
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </article>
  );
}
