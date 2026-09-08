"use client";

import { useEffect, useMemo, useRef } from "react";

import { useAppStore } from "@/store/useAppStore";
import { useUIStore } from "@/store/useUIStore";
import { BookOpen, Stack, X } from "@/components/ui/icons";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { ChatContextPanel } from "./ChatContextPanel";
import { PassageCard } from "./PassageCard";

export function RightPanel() {
  const { rightWidth, rightOpen, setRightWidth, toggleRight } = useUIStore();
  const streaming = useAppStore((s) => s.streaming);
  const activeAnswer = useAppStore((s) => s.activeAnswer);
  const streamingChunks = useAppStore((s) => s.streamingChunks);
  const highlightedChunkId = useAppStore((s) => s.highlightedChunkId);

  const rawChunks = activeAnswer?.sourceChunks ?? streamingChunks;
  const citationByChunk = useMemo(
    () => new Map((activeAnswer?.citations ?? []).map((c) => [c.chunkId, c])),
    [activeAnswer],
  );
  const chunks = useMemo(
    () =>
      rawChunks
        .map((c, i) => ({ c, i, marker: citationByChunk.get(c.chunkId)?.marker }))
        .sort((a, b) => {
          if (a.marker != null && b.marker != null) return a.marker - b.marker;
          if (a.marker != null) return -1;
          if (b.marker != null) return 1;
          return a.i - b.i;
        })
        .map(({ c }) => c),
    [rawChunks, citationByChunk],
  );
  const rankByChunk = useMemo(() => new Map(rawChunks.map((c, i) => [c.chunkId, i + 1])), [rawChunks]);
  const refs = useRef<Map<string, HTMLElement>>(new Map());

  useEffect(() => {
    if (!highlightedChunkId) return;
    refs.current.get(highlightedChunkId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = setTimeout(() => useAppStore.getState().highlightChunk(null), 1600);
    return () => clearTimeout(t);
  }, [highlightedChunkId]);

  if (!rightOpen) {
    return (
      <button
        onClick={toggleRight}
        className="flex w-9 shrink-0 flex-col items-center gap-2 border-l border-line bg-surface-raised pt-3 text-content-muted transition-colors hover:text-content-primary"
        aria-label="Show sources"
      >
        <Stack className="h-4 w-4" />
        <span className="[writing-mode:vertical-rl] text-2xs tracking-wide">sources</span>
      </button>
    );
  }

  const empty = !activeAnswer && !chunks.length;
  const ungrounded = activeAnswer && !activeAnswer.grounded && activeAnswer.retrievalMode !== "meta";

  return (
    <>
      <ResizeHandle side="right" width={rightWidth} onResize={setRightWidth} />
      <aside
        className="flex shrink-0 flex-col border-l border-line bg-surface-raised"
        style={{ width: rightWidth }}
      >
        <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
          <Stack className="h-3.5 w-3.5 text-content-muted" />
          <span className="text-xs font-medium text-content-primary">
            Sources{chunks.length ? ` · ${chunks.length}` : ""}
          </span>
          <button
            onClick={toggleRight}
            className="ml-auto rounded p-1 text-content-muted hover:text-content-primary"
            aria-label="Hide panel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <ChatContextPanel />

        <div className="flex-1 overflow-y-auto">
          {empty ? (
            <div className="flex h-full flex-col items-center justify-center gap-2.5 px-9 text-center">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-surface-sunken text-content-muted">
                <BookOpen className="h-4 w-4" />
              </span>
              <p className="text-sm font-medium text-content-secondary">Nothing to cite yet</p>
              <p className="max-w-[26ch] text-2xs leading-relaxed text-content-muted">
                Ask about a topic your uploaded notes cover and the exact passages the explanation
                draws on show up here — cited ones marked with their [n].
              </p>
            </div>
          ) : (
            <div className="stagger space-y-2 p-3">
              {ungrounded && (
                <p className="rounded-md border border-caution/25 bg-caution/8 p-2.5 text-2xs leading-relaxed text-caution">
                  This answer came from general knowledge — nothing in your materials matched.
                </p>
              )}
              {chunks.map((c) => (
                <PassageCard
                  key={c.chunkId}
                  chunk={c}
                  rank={rankByChunk.get(c.chunkId) ?? 0}
                  citation={citationByChunk.get(c.chunkId)}
                  highlighted={highlightedChunkId === c.chunkId}
                  ref={(el) => {
                    if (el) refs.current.set(c.chunkId, el);
                    else refs.current.delete(c.chunkId);
                  }}
                />
              ))}
              {streaming && !chunks.length && <div className="skeleton h-24" />}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
