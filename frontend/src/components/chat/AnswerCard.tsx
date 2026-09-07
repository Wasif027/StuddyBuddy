"use client";

import { useState } from "react";

import type { ChatMessage } from "@/lib/types";
import { cn, copyToClipboard, formatMs } from "@/lib/utils";
import { toast } from "@/store/useToast";
import { useAppStore } from "@/store/useAppStore";
import { ConfidenceBadge } from "@/components/ui/ConfidenceGauge";
import { ArrowElbowDownRight, ChartBar, Check, Copy, GitCompare, Sparkle, Spinner, Warning } from "@/components/ui/icons";
import { AnswerText } from "./AnswerText";

export function AnswerCard({ message }: { message: ChatMessage }) {
  const highlightChunk = useAppStore((s) => s.highlightChunk);
  const ask = useAppStore((s) => s.ask);
  const streaming = useAppStore((s) => s.streaming);
  const [copied, setCopied] = useState(false);
  const answer = message.answer;

  const onCite = (marker: number) => {
    const c = answer?.citations.find((x) => x.marker === marker);
    if (c) highlightChunk(c.chunkId);
  };

  if (message.error) {
    return (
      <div className="card border-danger/35 bg-danger/6 p-4">
        <p className="flex items-center gap-2 text-sm font-medium text-danger">
          <Warning className="h-4 w-4" weight="fill" /> Could not answer
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-content-secondary">{message.error}</p>
      </div>
    );
  }

  const skeleton = message.pending && !message.content;

  return (
    <div className="rounded-xl border border-line bg-surface-raised p-5 shadow-[0_1px_2px_rgb(var(--shadow)/0.04),0_18px_44px_-22px_rgb(var(--shadow)/0.16)]">
      {answer?.compareMode && (
        <p className="mb-3 inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-1 text-2xs font-medium text-accent">
          <GitCompare className="h-3 w-3" weight="fill" /> comparing documents
        </p>
      )}
      {answer && !answer.compareMode && answer.retrievalMode !== "pinpoint" && answer.retrievalMode !== "meta" && (
        <p
          className={cn(
            "mb-3 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-2xs font-medium",
            answer.retrievalMode === "analysis"
              ? "bg-accent-soft text-accent"
              : "bg-surface-sunken text-content-secondary",
          )}
          title={answer.retrievalNote}
        >
          {answer.retrievalMode === "analysis" ? (
            <ChartBar className="h-3 w-3" weight="fill" />
          ) : (
            <Sparkle className="h-3 w-3" weight="fill" />
          )}
          {answer.retrievalMode === "analysis"
            ? "computed answer"
            : answer.retrievalMode === "document"
              ? "full-document read"
              : "broad scan"}
          {answer.retrievalMode === "analysis" && answer.analysis?.tablesUsed?.length
            ? ` · ${answer.analysis.tablesUsed.join(", ")}`
            : ""}
        </p>
      )}
      {skeleton ? (
        <div className="space-y-2.5">
          <div className="skeleton h-3 w-2/3" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-11/12" />
          <div className="skeleton h-3 w-4/5" />
          <p className="flex items-center gap-1.5 pt-1 text-2xs text-content-muted">
            <Spinner className="h-3 w-3 animate-spin" /> retrieving &amp; reranking passages
          </p>
        </div>
      ) : (
        <AnswerText
          text={message.content}
          citations={answer?.citations ?? []}
          onCite={onCite}
          streaming={message.pending}
        />
      )}

      {answer && !message.pending && (
        <>
          {answer.insufficientEvidence && (
            <p className="mt-3.5 flex items-start gap-2 rounded-md border border-caution/25 bg-caution/8 p-2.5 text-2xs leading-relaxed text-caution">
              <Warning className="mt-px h-3 w-3 shrink-0" weight="fill" />
              Thin evidence in your documents — double-check this, or add a document that covers it.
            </p>
          )}

          {answer.followUps.length > 0 && (
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {answer.followUps.map((f) => (
                <button
                  key={f}
                  disabled={streaming}
                  onClick={() => ask(f, {})}
                  className="chip transition-[border-color,color] hover:border-accent/50 hover:text-accent disabled:opacity-50"
                >
                  <ArrowElbowDownRight className="h-3 w-3" />
                  {f}
                </button>
              ))}
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line pt-3 text-2xs text-content-muted">
            {answer.retrievalMode !== "meta" && (
              <>
                <ConfidenceBadge value={answer.confidence} label={answer.confidenceLabel} />
                <span className="tnum">{answer.citations.length} cited</span>
                <span aria-hidden>·</span>
              </>
            )}
            <span className="font-mono">{answer.model}</span>
            <span aria-hidden>·</span>
            <span className="tnum">{formatMs(answer.latencyMs)}</span>
            {answer.cached && <span className="chip py-0.5">cached</span>}
            <button
              onClick={async () => {
                if (await copyToClipboard(toMarkdown(message))) {
                  setCopied(true);
                  toast.success("Copied as Markdown");
                  setTimeout(() => setCopied(false), 1400);
                }
              }}
              className="ml-auto flex items-center gap-1 transition-colors hover:text-content-primary"
            >
              {copied ? <Check className="h-3 w-3" weight="bold" /> : <Copy className="h-3 w-3" />}
              Copy
            </button>
          </div>
        </>
      )}

      {message.pending && message.content && (
        <p className="mt-2.5 flex items-center gap-1.5 text-2xs text-content-muted">
          <Spinner className="h-3 w-3 animate-spin" /> streaming
        </p>
      )}
    </div>
  );
}

function toMarkdown(m: ChatMessage): string {
  const a = m.answer;
  if (!a) return m.content;
  const cites = a.citations.map((c) => `[${c.marker}] ${c.title}${c.quote ? ` — "${c.quote}"` : ""}`).join("\n");
  return `**Q:** ${a.question}\n\n${a.answer}\n\n---\n**Confidence:** ${(a.confidence * 100).toFixed(0)}% (${a.confidenceLabel})  ·  **Model:** ${a.model}\n\n**Sources**\n${cites}`;
}
