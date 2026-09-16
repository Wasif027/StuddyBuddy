"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { copyToClipboard, downloadBlob, formatMs } from "@/lib/utils";
import { toast } from "@/store/useToast";
import { useAppStore } from "@/store/useAppStore";
import { useStudyStore } from "@/store/useStudyStore";
import {
  ArrowElbowDownRight,
  BookOpen,
  Check,
  Copy,
  Exam,
  GitCompare,
  NotePencil,
  Refresh,
  Sparkle,
  Spinner,
  UploadSimple,
  Warning,
} from "@/components/ui/icons";
import { AnswerText } from "./AnswerText";
import { ChartView } from "./ChartView";

export function AnswerCard({ message }: { message: ChatMessage }) {
  const highlightChunk = useAppStore((s) => s.highlightChunk);
  const ask = useAppStore((s) => s.ask);
  const streaming = useAppStore((s) => s.streaming);
  const groundingDone = useAppStore((s) => s.groundingDone);
  const streamingChunks = useAppStore((s) => s.streamingChunks);
  const activeId = useAppStore((s) => s.activeId);
  const generate = useStudyStore((s) => s.generatePracticeSet);
  const generating = useStudyStore((s) => s.generating);
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const answer = message.answer;

  const onCite = (marker: number) => {
    const c = answer?.citations.find((x) => x.marker === marker);
    if (c) highlightChunk(c.chunkId);
  };

  if (message.error) {
    return (
      <div className="card border-danger/35 bg-danger/6 p-4">
        <p className="flex items-center gap-2 text-sm font-medium text-danger">
          <Warning className="h-4 w-4" weight="fill" /> Something went wrong
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-content-secondary">{message.error}</p>
      </div>
    );
  }

  const skeleton = message.pending && !message.content;
  const isMeta = answer?.retrievalMode === "meta";
  const modeChip =
    answer && !isMeta && answer.retrievalMode === "document"
      ? "full read of your material"
      : answer?.retrievalMode === "overview"
        ? "across your materials"
        : null;

  const saveNote = async () => {
    if (!answer?.messageId) return;
    setSaving(true);
    try {
      await api.saveFromChat({ messageId: answer.messageId });
      toast.success("Saved to notes");
    } catch (err) {
      toast.error("Couldn't save", err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const downloadPdf = async () => {
    if (!answer) return;
    try {
      const blob = await api.exportMarkdown({
        format: "pdf",
        title: answer.question.slice(0, 80),
        markdown: `**Question:** ${answer.question}\n\n${answer.answer}`,
      });
      downloadBlob(blob, "studybuddy-answer.pdf");
    } catch (err) {
      toast.error("Couldn't make the PDF", err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div
      className="rounded-xl border border-line bg-surface-raised shadow-[0_1px_2px_rgb(var(--shadow)/0.04),0_18px_44px_-22px_rgb(var(--shadow)/0.16)]"
      style={{ padding: "calc(var(--space-scale, 1) * 1.25rem)" }}
    >
      {answer?.compareMode && (
        <p className="mb-3 inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-1 text-2xs font-medium text-accent">
          <GitCompare className="h-3 w-3" weight="fill" /> comparing materials
        </p>
      )}
      {modeChip && (
        <p
          className="mb-3 inline-flex items-center gap-1.5 rounded-md bg-surface-sunken px-2 py-1 text-2xs font-medium text-content-secondary"
          title={answer?.retrievalNote}
        >
          <Sparkle className="h-3 w-3" weight="fill" /> {modeChip}
        </p>
      )}
      {answer?.corrected && (
        <p className="mb-3 inline-flex items-center gap-1.5 rounded-md bg-accent-soft px-2 py-1 text-2xs font-medium text-accent">
          <Refresh className="h-3 w-3" weight="bold" /> correcting an earlier answer
        </p>
      )}

      {skeleton ? (
        <div className="space-y-2.5">
          <div className="skeleton h-3 w-2/3" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-11/12" />
          <div className="skeleton h-3 w-4/5" />
          <p className="flex items-center gap-1.5 pt-1 text-2xs text-content-muted">
            <Spinner className="h-3 w-3 animate-spin" />
            {groundingDone && streamingChunks.length === 0
              ? "answering from general knowledge"
              : "reading your materials"}
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
          {answer.chart && <ChartView chart={answer.chart} />}

          {!isMeta && !answer.grounded && !answer.insufficientEvidence && (
            <p className="mt-3.5 flex items-start gap-2 rounded-md border border-caution/25 bg-caution/8 p-2.5 text-2xs leading-relaxed text-caution">
              <BookOpen className="mt-px h-3 w-3 shrink-0" weight="fill" />
              Answered from general knowledge — this isn&apos;t from your uploaded materials.
            </p>
          )}

          {answer.followUps.length > 0 && (
            <div className="mt-3.5 flex flex-wrap gap-1.5">
              {answer.followUps.map((f) => (
                <button
                  key={f}
                  disabled={streaming}
                  onClick={() => ask(f)}
                  className="chip transition-[border-color,color] hover:border-accent/50 hover:text-accent disabled:opacity-50"
                >
                  <ArrowElbowDownRight className="h-3 w-3" />
                  {f}
                </button>
              ))}
            </div>
          )}

          {!isMeta && (
            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line pt-3 text-2xs text-content-muted">
              {answer.grounded && (
                <span className="inline-flex items-center gap-1 font-medium text-positive">
                  <Check className="h-3 w-3" weight="bold" /> {answer.citations.length} from your notes
                </span>
              )}
              <span className="chip py-0.5 capitalize">{answer.explainLevel}</span>
              <span className="tnum">{formatMs(answer.latencyMs)}</span>
              {answer.cached && <span className="chip py-0.5">cached</span>}

              <div className="ml-auto flex items-center gap-3">
                <button
                  onClick={() => generate({ conversationId: activeId ?? undefined, topic: answer.question })}
                  disabled={generating || streaming}
                  className="flex items-center gap-1 transition-colors hover:text-accent disabled:opacity-50"
                >
                  <Exam className="h-3 w-3" /> Practice this
                </button>
                <button
                  onClick={saveNote}
                  disabled={saving}
                  className="flex items-center gap-1 transition-colors hover:text-content-primary disabled:opacity-50"
                >
                  <NotePencil className="h-3 w-3" /> Save
                </button>
                <button
                  onClick={downloadPdf}
                  className="flex items-center gap-1 transition-colors hover:text-content-primary"
                >
                  <UploadSimple className="h-3 w-3 rotate-180" /> PDF
                </button>
                <button
                  onClick={async () => {
                    if (await copyToClipboard(toMarkdown(message))) {
                      setCopied(true);
                      toast.success("Copied as Markdown");
                      setTimeout(() => setCopied(false), 1400);
                    }
                  }}
                  className="flex items-center gap-1 transition-colors hover:text-content-primary"
                >
                  {copied ? <Check className="h-3 w-3" weight="bold" /> : <Copy className="h-3 w-3" />}
                  Copy
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {message.pending && message.content && (
        <p className="mt-2.5 flex items-center gap-1.5 text-2xs text-content-muted">
          <Spinner className="h-3 w-3 animate-spin" /> writing
        </p>
      )}
    </div>
  );
}

function toMarkdown(m: ChatMessage): string {
  const a = m.answer;
  if (!a) return m.content;
  const cites = a.citations
    .map((c) => `[${c.marker}] ${c.title}${c.quote ? ` — "${c.quote}"` : ""}`)
    .join("\n");
  return `**Q:** ${a.question}\n\n${a.answer}${cites ? `\n\n---\n**Sources**\n${cites}` : ""}`;
}
