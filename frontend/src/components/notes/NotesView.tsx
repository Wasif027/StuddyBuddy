"use client";

import { useEffect, useMemo, useState } from "react";

import type { NoteKind, NoteRead, RoutineDay } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { useStudyStore } from "@/store/useStudyStore";
import { AnswerText } from "@/components/chat/AnswerText";
import {
  CalendarBlank,
  Exam,
  NotePencil,
  Plus,
  PushPin,
  Spinner,
  Trash,
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
  const [filter, setFilter] = useState<NoteKind | "all">("all");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");

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

  const addNote = async () => {
    if (!draftTitle.trim()) return;
    await create({ title: draftTitle.trim(), kind: "note" });
    setDraftTitle("");
    setCreating(false);
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-5xl gap-5 px-5 py-8">
      <div className="w-72 shrink-0">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight text-content-primary">Notes</h1>
          <button
            onClick={() => setCreating((v) => !v)}
            className="btn btn-ghost h-7 w-7 !p-0 text-content-muted"
            aria-label="New note"
          >
            <Plus className="h-4 w-4" weight="bold" />
          </button>
        </div>

        {creating && (
          <div className="mt-2 flex gap-1">
            <input
              autoFocus
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addNote()}
              placeholder="Note title"
              className="input py-1.5 text-xs"
            />
            <button onClick={addNote} className="btn btn-accent h-8 px-2 text-xs">
              Add
            </button>
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
            <button
              key={n.id}
              onClick={() => setSelectedId(n.id)}
              className={cn(
                "flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left transition-colors",
                selectedId === n.id ? "bg-accent-soft" : "hover:bg-surface-sunken",
              )}
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
          ))}
        </div>
      </div>

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
    </div>
  );
}

function NoteDetail({ note }: { note: NoteRead }) {
  const update = useStudyStore((s) => s.updateNote);
  const del = useStudyStore((s) => s.deleteNote);
  const quiz = useStudyStore((s) => s.quizFromNote);
  const generating = useStudyStore((s) => s.generating);
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(note.bodyMd);

  useEffect(() => {
    setBody(note.bodyMd);
    setEditing(false);
  }, [note.id, note.bodyMd]);

  const days = (note.structured?.days as RoutineDay[] | undefined) ?? [];

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
                onClick={() => {
                  update(note.id, { bodyMd: body });
                  setEditing(false);
                }}
                className="btn btn-accent h-8 px-3 text-xs"
              >
                Save
              </button>
              <button onClick={() => setEditing(false)} className="btn h-8 px-3 text-xs">
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
              <button
                onClick={() => quiz(note.id)}
                disabled={generating}
                className="btn h-8 px-3 text-xs"
              >
                {generating ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Exam className="h-3.5 w-3.5" />}
                Quiz me on this
              </button>
            </div>
          </>
        )}
      </div>
    </article>
  );
}
