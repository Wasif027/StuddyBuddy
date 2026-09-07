"use client";

import { useState } from "react";

import type { Suggestion, SuggestionPriority } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { Check, Lightning, PencilSimple, ThumbsDown, X } from "@/components/ui/icons";

const PRIORITY: Record<SuggestionPriority, { dot: string; label: string }> = {
  high: { dot: "bg-danger", label: "high" },
  medium: { dot: "bg-caution", label: "medium" },
  low: { dot: "bg-content-muted", label: "low" },
};

const DECIDED: Record<string, { label: string; tone: string }> = {
  accepted: { label: "Accepted", tone: "text-positive" },
  rejected: { label: "Rejected", tone: "text-content-muted" },
  done: { label: "Already done", tone: "text-content-secondary" },
};

export function SuggestionCard({ suggestion: s, messageId }: { suggestion: Suggestion; messageId: string }) {
  const decide = useAppStore((st) => st.decideSuggestion);
  const runSuggestion = useAppStore((st) => st.runSuggestion);
  const streaming = useAppStore((st) => st.streaming);
  const [busy, setBusy] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState(s.note ?? "");

  const pending = s.decision === "pending";
  const decided = DECIDED[s.decision];

  const run = async (d: "accept" | "reject" | "done") => {
    setBusy(true);
    await decide(messageId, s.id, d, note.trim() || undefined);
    setBusy(false);
    setNoteOpen(false);
  };

  const runIt = async () => {
    setBusy(true);
    await runSuggestion(messageId, s);
    setBusy(false);
  };

  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        s.rejectDepth > 0 ? "border-accent/30 bg-accent-soft/40" : "border-line bg-surface-raised",
        !pending && "opacity-90",
      )}
    >
      {s.rejectDepth > 0 && (
        <p className="mb-1 text-[0.58rem] font-medium uppercase tracking-wide text-accent">
          Alternative
        </p>
      )}
      <div className="flex items-start gap-2">
        <span className={cn("mt-1 h-1.5 w-1.5 shrink-0 rounded-full", PRIORITY[s.priority].dot)} />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium leading-snug text-content-primary">{s.text}</p>
          {s.rationale && (
            <p className="mt-1 text-[0.68rem] leading-snug text-content-muted">{s.rationale}</p>
          )}
        </div>
      </div>

      {noteOpen && pending && (
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="Add a note (optional)…"
          className="mt-2 w-full rounded-md border border-line bg-surface-base px-2 py-1.5 text-2xs focus:border-accent/50 focus:outline-none"
        />
      )}

      {s.kind === "explore" && pending && (
        <button
          onClick={runIt}
          disabled={busy || streaming}
          title="Ask this as a question and drop the grounded answer into the chat"
          className="btn btn-accent mt-2.5 w-full justify-center py-1 text-2xs disabled:opacity-50"
        >
          <Lightning className="h-3 w-3" weight="fill" /> Run — answer this from your documents
        </button>
      )}

      {pending ? (
        <div className="mt-2 flex items-center gap-1.5">
          <button
            onClick={() => run("accept")}
            disabled={busy}
            className={cn(
              "btn px-2 py-1 text-2xs disabled:opacity-50",
              s.kind !== "explore" && "btn-accent",
            )}
          >
            <Check className="h-3 w-3" weight="bold" /> Accept
          </button>
          <button
            onClick={() => run("reject")}
            disabled={busy}
            className="btn px-2 py-1 text-2xs disabled:opacity-50"
          >
            <ThumbsDown className="h-3 w-3" /> Reject
          </button>
          <button
            onClick={() => run("done")}
            disabled={busy}
            className="btn px-2 py-1 text-2xs disabled:opacity-50"
          >
            Already done
          </button>
          <button
            onClick={() => setNoteOpen((v) => !v)}
            className="ml-auto p-1 text-content-muted hover:text-content-primary"
            aria-label="Add a note"
          >
            {noteOpen ? <X className="h-3 w-3" /> : <PencilSimple className="h-3 w-3" />}
          </button>
        </div>
      ) : (
        <div className="mt-2 flex items-center gap-2 text-2xs">
          <span className={cn("font-medium", decided?.tone)}>{decided?.label}</span>
          {s.note && <span className="text-content-muted">· {s.note}</span>}
        </div>
      )}
    </div>
  );
}
