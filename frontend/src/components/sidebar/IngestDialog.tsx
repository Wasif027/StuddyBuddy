"use client";

import { useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useUIStore } from "@/store/useUIStore";
import { Modal } from "@/components/ui/Modal";
import { ImageIcon, Spinner, UploadSimple } from "@/components/ui/icons";

type Mode = "upload" | "image" | "paste";

export function IngestDialog() {
  const open = useUIStore((s) => s.ingestOpen);
  const onClose = () => useUIStore.getState().setIngestOpen(false);
  const ingestText = useAppStore((s) => s.ingestText);
  const uploadDoc = useAppStore((s) => s.uploadDoc);
  const categories = useAppStore((s) => s.categories);

  const [mode, setMode] = useState<Mode>("upload");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [hint, setHint] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setTitle("");
    setContent("");
    setHint("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const submit = async () => {
    setBusy(true);
    let ok = false;
    if (mode === "paste") {
      ok = await ingestText({ title: title.trim(), content: content.trim(), category: category || null });
    } else if (file) {
      const res = await uploadDoc(file, { category: category || null, title: title.trim() || undefined, hint: hint.trim() || undefined });
      ok = res.ok;
    }
    setBusy(false);
    if (ok) {
      reset();
      onClose();
    }
  };

  const canSubmit =
    mode === "paste" ? title.trim().length > 1 && content.trim().length > 20 : !!file;

  const accept = mode === "image" ? ".png,.jpg,.jpeg,.webp" : ".pdf,.docx,.pptx";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add a study material"
      description="Upload a document, snap a photo of a diagram / problem / your timetable, or paste some text. It's added to your materials and you can ask about it right away."
    >
      <div className="mb-4 flex gap-1 rounded-lg bg-surface-sunken p-1">
        {(["upload", "image", "paste"] as const).map((m) => (
          <button
            key={m}
            onClick={() => {
              setMode(m);
              setFile(null);
            }}
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              mode === m ? "bg-surface-raised text-content-primary shadow-sm" : "text-content-muted",
            )}
          >
            {m === "upload" ? "Document" : m === "image" ? "Photo" : "Paste text"}
          </button>
        ))}
      </div>

      <div className="space-y-3.5">
        <div>
          <label className="label mb-1 block">Subject</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className="input">
            <option value="">— pick a subject (or leave to auto-detect) —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.slug}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {mode === "paste" ? (
          <>
            <div>
              <label className="label mb-1 block">Title</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Chapter 4 — cell division"
                className="input"
              />
            </div>
            <div>
              <label className="label mb-1 block">Text</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={9}
                placeholder="Paste your notes, a definition sheet, an article…"
                className="input font-mono text-2xs leading-relaxed"
              />
            </div>
          </>
        ) : (
          <>
            <button
              onClick={() => fileRef.current?.click()}
              className="flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-line-strong bg-surface-sunken/40 px-4 py-9 text-center transition-colors hover:border-accent/60"
            >
              {mode === "image" ? (
                <ImageIcon className="h-6 w-6 text-content-muted" />
              ) : (
                <UploadSimple className="h-6 w-6 text-content-muted" />
              )}
              <span className="text-sm font-medium text-content-secondary">
                {file
                  ? file.name
                  : mode === "image"
                    ? "Choose a photo — a diagram, a worked problem, your notes, or a timetable"
                    : "Choose a PDF, Word doc or PowerPoint"}
              </span>
              <span className="text-2xs text-content-muted">
                {mode === "image" ? ".png · .jpg · .webp" : ".pdf · .docx · .pptx"} — up to 20 MB
              </span>
              <input
                ref={fileRef}
                type="file"
                accept={accept}
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </button>
            {mode === "image" && (
              <div>
                <label className="label mb-1 block">Anything I should know? (optional)</label>
                <input
                  value={hint}
                  onChange={(e) => setHint(e.target.value)}
                  placeholder="e.g. “I got stuck on part b” or “this is my exam timetable”"
                  className="input"
                />
              </div>
            )}
          </>
        )}
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <button onClick={onClose} className="btn text-xs">
          Cancel
        </button>
        <button onClick={submit} disabled={!canSubmit || busy} className="btn btn-accent text-xs">
          {busy && <Spinner className="h-3.5 w-3.5 animate-spin" />}
          {mode === "paste" ? "Add" : mode === "image" ? "Read it" : "Upload"}
        </button>
      </div>
    </Modal>
  );
}
