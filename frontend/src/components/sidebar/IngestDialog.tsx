"use client";

import { useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { Modal } from "@/components/ui/Modal";
import { Spinner, UploadSimple } from "@/components/ui/icons";

const CATEGORIES = [
  "policy",
  "contract",
  "runbook",
  "tech-doc",
  "meeting-notes",
  "incident",
  "security",
  "sales",
  "data",
  "deck",
  "hr",
  "finance",
  "legal",
];

export function IngestDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ingestText = useAppStore((s) => s.ingestText);
  const uploadDoc = useAppStore((s) => s.uploadDoc);

  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("policy");
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setTitle("");
    setContent("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const submit = async () => {
    setBusy(true);
    const ok =
      mode === "paste"
        ? await ingestText({ title: title.trim(), content: content.trim(), category })
        : file
          ? await uploadDoc(file, category)
          : false;
    setBusy(false);
    if (ok) {
      reset();
      onClose();
    }
  };

  const canSubmit =
    mode === "paste" ? title.trim().length > 1 && content.trim().length > 20 : !!file;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add a document"
      description="Upload a file or paste some text. It's added to your knowledge base and you can ask questions about it right away."
    >
      <div className="mb-4 flex gap-1 rounded-lg bg-surface-sunken p-1">
        {(["paste", "upload"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              "flex-1 rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors",
              mode === m ? "bg-surface-raised text-content-primary shadow-sm" : "text-content-muted",
            )}
          >
            {m === "paste" ? "Paste text" : "Upload file"}
          </button>
        ))}
      </div>

      <div className="space-y-3.5">
        <div>
          <label className="label mb-1 block">Category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className="input">
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
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
                placeholder="Q3 finance review"
                className="input"
              />
            </div>
            <div>
              <label className="label mb-1 block">Text</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={9}
                placeholder={"Paste your notes, policy text, FAQ answers…"}
                className="input font-mono text-2xs leading-relaxed"
              />
            </div>
          </>
        ) : (
          <button
            onClick={() => fileRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-line-strong bg-surface-sunken/40 px-4 py-9 text-center transition-colors hover:border-accent/60"
          >
            <UploadSimple className="h-6 w-6 text-content-muted" />
            <span className="text-sm font-medium text-content-secondary">
              {file ? file.name : "Choose a PDF, Word, Excel or PowerPoint file"}
            </span>
            <span className="text-2xs text-content-muted">
              .pdf · .docx · .xlsx / .xls · .pptx — up to 15 MB. Google Sheets/Slides: use File → Download.
            </span>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.xlsx,.xls,.pptx"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </button>
        )}
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <button onClick={onClose} className="btn text-xs">
          Cancel
        </button>
        <button onClick={submit} disabled={!canSubmit || busy} className="btn btn-accent text-xs">
          {busy && <Spinner className="h-3.5 w-3.5 animate-spin" />}
          {mode === "upload" ? "Upload" : "Add"}
        </button>
      </div>
    </Modal>
  );
}
