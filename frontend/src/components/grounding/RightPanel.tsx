"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useUIStore } from "@/store/useUIStore";
import { ConfidenceGauge } from "@/components/ui/ConfidenceGauge";
import { SuggestionCard } from "@/components/suggestions/SuggestionCard";
import { ChartBar, GitCompare, ListChecks, Sparkle, Stack, X, type Icon } from "@/components/ui/icons";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import { AnalysisCard } from "./AnalysisCard";
import { PassageCard } from "./PassageCard";

type Tab = "grounding" | "next";

export function RightPanel() {
  const { rightWidth, rightOpen, setRightWidth, toggleRight } = useUIStore();
  const streaming = useAppStore((s) => s.streaming);
  const activeAnswer = useAppStore((s) => s.activeAnswer);
  const streamingChunks = useAppStore((s) => s.streamingChunks);
  const streamingAnalysis = useAppStore((s) => s.streamingAnalysis);
  const streamingSuggestions = useAppStore((s) => s.streamingSuggestions);
  const highlightedChunkId = useAppStore((s) => s.highlightedChunkId);
  const messages = useAppStore((s) => s.messages);
  const [tab, setTab] = useState<Tab>("grounding");

  const analysis = activeAnswer?.analysis ?? streamingAnalysis;
  const suggestions = useMemo(
    () => (activeAnswer?.suggestions?.length ? activeAnswer.suggestions : streamingSuggestions),
    [activeAnswer, streamingSuggestions],
  );

  const owningMessageId = useMemo(
    () => messages.find((m) => m.answer && activeAnswer && m.answer.id === activeAnswer.id)?.id ?? "",
    [messages, activeAnswer],
  );

  const rawChunks = activeAnswer?.sourceChunks ?? streamingChunks;
  const citationByChunk = useMemo(
    () => new Map((activeAnswer?.citations ?? []).map((c) => [c.chunkId, c])),
    [activeAnswer],
  );
  // Cited passages first, in marker order (so the panel reads [1] [2] [3]); the
  // rest keep their retrieval order below.
  const chunks = useMemo(() => {
    return rawChunks
      .map((c, i) => ({ c, i, marker: citationByChunk.get(c.chunkId)?.marker }))
      .sort((a, b) => {
        if (a.marker != null && b.marker != null) return a.marker - b.marker;
        if (a.marker != null) return -1;
        if (b.marker != null) return 1;
        return a.i - b.i;
      })
      .map(({ c }) => c);
  }, [rawChunks, citationByChunk]);
  const rankByChunk = useMemo(
    () => new Map(rawChunks.map((c, i) => [c.chunkId, i + 1])),
    [rawChunks],
  );
  const refs = useRef<Map<string, HTMLElement>>(new Map());

  useEffect(() => {
    if (!highlightedChunkId) return;
    refs.current.get(highlightedChunkId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = setTimeout(() => useAppStore.getState().highlightChunk(null), 1600);
    return () => clearTimeout(t);
  }, [highlightedChunkId]);

  useEffect(() => {
    if (suggestions.some((s) => s.decision === "pending")) setTab("next");
  }, [suggestions]);

  if (!rightOpen) {
    return (
      <button
        onClick={toggleRight}
        className="flex w-9 shrink-0 flex-col items-center gap-2 border-l border-line bg-surface-raised pt-3 text-content-muted transition-colors hover:text-content-primary"
        aria-label="Show grounding panel"
      >
        <Stack className="h-4 w-4" />
        <span className="[writing-mode:vertical-rl] text-2xs tracking-wide">grounding</span>
      </button>
    );
  }

  return (
    <>
      <ResizeHandle side="right" width={rightWidth} onResize={setRightWidth} />
      <aside className="flex shrink-0 flex-col border-l border-line bg-surface-raised" style={{ width: rightWidth }}>
        <div className="flex items-center gap-1 border-b border-line px-2 py-2">
          <TabButton active={tab === "grounding"} onClick={() => setTab("grounding")} icon={Stack}>
            Grounding
          </TabButton>
          <TabButton active={tab === "next"} onClick={() => setTab("next")} icon={ListChecks}>
            Next steps{suggestions.length ? ` · ${suggestions.length}` : ""}
          </TabButton>
          <button
            onClick={toggleRight}
            className="ml-1 rounded p-1 text-content-muted hover:text-content-primary"
            aria-label="Hide panel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {tab === "grounding" ? (
          <div className="flex-1 overflow-y-auto">
            {!activeAnswer && !chunks.length && !analysis ? (
              <Empty
                icon={Sparkle}
                title="No answer yet"
                body="Ask a question to see the confidence score and the exact passages the answer is built from — the cited ones are marked with their [n]. Analytic questions over a spreadsheet show the computed result and the query."
              />
            ) : (
              <>
                <div className="border-b border-line px-4 py-4">
                  {activeAnswer ? (
                    <ConfidenceGauge value={activeAnswer.confidence} label={activeAnswer.confidenceLabel} />
                  ) : (
                    <p className="text-xs text-content-muted">
                      {analysis ? "Computing…" : "Retrieving evidence…"}
                    </p>
                  )}
                  {activeAnswer?.compareMode && (
                    <p className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-1 text-2xs text-accent">
                      <GitCompare className="h-3 w-3" weight="fill" /> comparing documents
                    </p>
                  )}
                  {analysis && (
                    <p className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-1 text-2xs text-accent">
                      <ChartBar className="h-3 w-3" weight="fill" /> computed from your data
                    </p>
                  )}
                </div>

                {analysis && (
                  <div className="border-b border-line p-3">
                    <AnalysisCard analysis={analysis} />
                  </div>
                )}

                <div className="stagger space-y-2 p-3">
                  {chunks.length > 0 && (
                    <p className="label px-1 pb-0.5">
                      {analysis ? "Supporting passages" : "Source passages"} ·{" "}
                      <span className="tnum">{chunks.length}</span>
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
              </>
            )}
          </div>
        ) : (
          <div className="stagger flex-1 space-y-2.5 overflow-y-auto p-3">
            {suggestions.length === 0 ? (
              <Empty
                icon={ListChecks}
                title="No next steps"
                body="When an answer implies something to do — reply to a customer, reprice a product, reorder stock — the assistant proposes it here. You accept, reject, or mark it already done. Nothing is executed."
              />
            ) : (
              <>
                <p className="px-1 text-2xs leading-relaxed text-content-muted">
                  Proposed next steps. Accept, reject, or mark as already done — nothing runs
                  automatically.
                </p>
                {suggestions.map((s) => (
                  <SuggestionCard key={s.id} suggestion={s} messageId={owningMessageId} />
                ))}
              </>
            )}
          </div>
        )}
      </aside>
    </>
  );
}

function TabButton({
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
        "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
        active ? "bg-surface-sunken text-content-primary" : "text-content-muted hover:text-content-primary",
      )}
    >
      <I className="h-3.5 w-3.5" weight={active ? "fill" : "regular"} />
      {children}
    </button>
  );
}

function Empty({ icon: I, title, body }: { icon: Icon; title: string; body: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2.5 px-9 text-center">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-surface-sunken text-content-muted">
        <I className="h-4 w-4" />
      </span>
      <p className="text-sm font-medium text-content-secondary">{title}</p>
      <p className="max-w-[26ch] text-2xs leading-relaxed text-content-muted">{body}</p>
    </div>
  );
}
