"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { ArrowUp, GitCompare, Lightning, Square, type Icon } from "@/components/ui/icons";

export function Composer() {
  const ask = useAppStore((s) => s.ask);
  const stop = useAppStore((s) => s.stop);
  const streaming = useAppStore((s) => s.streaming);
  const selectedCategoryId = useAppStore((s) => s.selectedCategoryId);
  const categories = useAppStore((s) => s.categories);
  const setCategory = useAppStore((s) => s.setCategory);
  const compareDocIds = useAppStore((s) => s.compareDocIds);
  const setCompareDocs = useAppStore((s) => s.setCompareDocs);
  const documents = useAppStore((s) => s.documents);

  const [text, setText] = useState("");
  const [fresh, setFresh] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 184)}px`;
  }, [text]);

  useEffect(() => {
    const onSlash = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "TEXTAREA" && tag !== "INPUT") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onSlash);
    return () => window.removeEventListener("keydown", onSlash);
  }, []);

  const submit = () => {
    const q = text.trim();
    if (!q || streaming) return;
    ask(q, { bypassCache: fresh });
    setText("");
  };

  const activeCategory = categories.find((c) => c.id === selectedCategoryId);
  const compareTitles = compareDocIds
    .map((id) => documents.find((d) => d.id === id)?.title)
    .filter(Boolean);
  const comparing = compareDocIds.length >= 2;

  return (
    <div className="border-t border-line bg-surface-raised">
      <div className="mx-auto w-full max-w-[46rem] px-5 py-4">
        {compareDocIds.length > 0 && (
          <div
            className={cn(
              "mb-2 flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-2xs",
              comparing ? "border-accent/30 bg-accent-soft text-accent" : "border-caution/30 bg-caution/8 text-caution",
            )}
          >
            <GitCompare className="h-3.5 w-3.5 shrink-0" weight="fill" />
            <span className="flex-1 truncate">
              {comparing
                ? `Comparing: ${compareTitles.join("  ·  ")}`
                : "Select at least 2 documents in the sidebar to compare"}
            </span>
            <button onClick={() => setCompareDocs([])} className="shrink-0 opacity-70 hover:opacity-100">
              clear
            </button>
          </div>
        )}
        <div className="rounded-xl border border-line bg-surface-base p-2.5 transition-colors focus-within:border-accent/50">
          <textarea
            ref={ref}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={
              streaming
                ? "Answering…"
                : comparing
                  ? "Ask how the selected documents differ…"
                  : "Ask a question about your documents…"
            }
            disabled={streaming}
            className="max-h-48 w-full resize-none bg-transparent px-1.5 pt-1 text-sm leading-relaxed text-content-primary placeholder:text-content-muted focus:outline-none disabled:opacity-60"
          />
          <div className="mt-1 flex items-center gap-1.5">
            <Toggle active={fresh} onClick={() => setFresh((v) => !v)} icon={Lightning}>
              Skip cache
            </Toggle>
            {activeCategory && (
              <button
                onClick={() => setCategory(null)}
                className="chip transition-colors hover:border-danger/50 hover:text-danger"
                title="Clear category scope"
              >
                {activeCategory.label}
                <span className="opacity-60">×</span>
              </button>
            )}
            <div className="ml-auto">
              {streaming ? (
                <button onClick={stop} className="btn btn-danger h-8 w-8 !p-0" aria-label="Stop generating">
                  <Square className="h-3 w-3" weight="fill" />
                </button>
              ) : (
                <button
                  onClick={submit}
                  disabled={!text.trim()}
                  className="btn btn-accent h-8 w-8 !p-0"
                  aria-label="Send question"
                >
                  <ArrowUp className="h-4 w-4" weight="bold" />
                </button>
              )}
            </div>
          </div>
        </div>
        <p className="mt-2 text-center text-[0.6rem] tracking-tight text-content-muted">
          <kbd className="font-mono">Enter</kbd> send · <kbd className="font-mono">⇧Enter</kbd> newline ·{" "}
          <kbd className="font-mono">⌘K</kbd> commands
        </p>
      </div>
    </div>
  );
}

function Toggle({
  active,
  onClick,
  icon: I,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: Icon;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-2xs font-medium transition-colors",
        active
          ? "border-accent/35 bg-accent-soft text-accent"
          : "border-line bg-surface-sunken text-content-muted hover:text-content-primary",
      )}
    >
      <I className="h-3 w-3" weight={active ? "fill" : "regular"} />
      {children}
    </button>
  );
}
