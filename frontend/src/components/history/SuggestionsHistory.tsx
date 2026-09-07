"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Suggestion, SuggestionDecision } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { toast } from "@/store/useToast";
import { ChatCircleDots, ListChecks, Spinner, X } from "@/components/ui/icons";

type Filter = "all" | SuggestionDecision;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "pending", label: "Pending" },
  { id: "accepted", label: "Accepted" },
  { id: "rejected", label: "Rejected" },
  { id: "done", label: "Done" },
];

const DOT: Record<SuggestionDecision, string> = {
  pending: "bg-accent",
  accepted: "bg-positive",
  rejected: "bg-content-muted",
  done: "bg-content-secondary",
};

export function SuggestionsHistory({ open, onClose }: { open: boolean; onClose: () => void }) {
  const openChat = useAppStore((s) => s.openChat);
  const [filter, setFilter] = useState<Filter>("all");
  const [rows, setRows] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api.listSuggestions(filter === "all" ? {} : { status: filter }));
    } catch (err) {
      toast.error("Couldn't load history", err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  const go = async (r: Suggestion) => {
    if (r.conversationDeleted || !r.conversationId) {
      toast.info("Conversation deleted", "The chat this suggestion came from no longer exists.");
      return;
    }
    onClose();
    await openChat(r.conversationId, r.messageId);
  };

  return (
    <div className="fixed inset-0 z-modal flex flex-col bg-surface-base">
      <header className="flex items-center gap-3 border-b border-line px-5 py-3">
        <ListChecks className="h-4 w-4 text-accent" weight="fill" />
        <h1 className="text-sm font-semibold tracking-tight text-content-primary">Suggestions</h1>
        <div className="ml-2 flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                "rounded-md px-2 py-1 text-2xs font-medium transition-colors",
                filter === f.id
                  ? "bg-accent-soft text-accent"
                  : "text-content-muted hover:text-content-primary",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          className="ml-auto rounded-md p-1.5 text-content-muted hover:bg-surface-sunken hover:text-content-primary"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto px-5 py-6">
        {loading ? (
          <p className="flex items-center gap-2 text-xs text-content-muted">
            <Spinner className="h-3.5 w-3.5 animate-spin" /> Loading…
          </p>
        ) : rows.length === 0 ? (
          <p className="py-16 text-center text-xs text-content-muted">
            Nothing here yet. Suggestions appear after the assistant answers a question that implies
            a next step.
          </p>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => go(r)}
                  className="group flex w-full items-start gap-3 rounded-lg border border-line bg-surface-raised p-3 text-left transition-colors hover:border-accent/40"
                >
                  <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", DOT[r.decision])} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium leading-snug text-content-primary">{r.text}</p>
                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.62rem] text-content-muted">
                      <span className="font-medium capitalize text-content-secondary">{r.decision}</span>
                      {r.note && <span>· {r.note}</span>}
                      <span>· {formatRelativeTime(r.createdAt ?? "")}</span>
                      <span className="inline-flex items-center gap-1">
                        ·
                        <ChatCircleDots className="h-3 w-3" />
                        {r.conversationDeleted ? (
                          <span className="italic">conversation deleted</span>
                        ) : (
                          <span className="truncate">{r.conversationTitle ?? "chat"}</span>
                        )}
                      </span>
                    </p>
                    {r.question && (
                      <p className="mt-1 truncate text-[0.6rem] text-content-muted/80">
                        from: “{r.question}”
                      </p>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
