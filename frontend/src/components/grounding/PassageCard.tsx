"use client";

import { forwardRef, useMemo, useState } from "react";

import type { Citation, SourceChunk } from "@/lib/types";
import { cn, copyToClipboard, scorePercent } from "@/lib/utils";
import { toast } from "@/store/useToast";
import { ChartBar, Copy, PresentationChart, Table } from "@/components/ui/icons";
import { ScoreBar } from "@/components/ui/ScoreBar";

/** Render `text` with the cited `quote` (if present) wrapped in a highlight. */
function highlight(text: string, quote?: string) {
  if (!quote) return text;
  const norm = quote.trim().replace(/\s+/g, " ");
  const idx = text.replace(/\s+/g, " ").toLowerCase().indexOf(norm.toLowerCase());
  if (idx < 0 || norm.length < 8) return text;
  // map back to original string roughly by walking words
  const before = text.slice(0, idx);
  const mid = text.slice(idx, idx + norm.length);
  const after = text.slice(idx + norm.length);
  return (
    <>
      {before}
      <mark className="rounded-sm bg-accent/20 px-0.5 text-content-primary">{mid}</mark>
      {after}
    </>
  );
}

export const PassageCard = forwardRef<
  HTMLElement,
  { chunk: SourceChunk; rank: number; citation?: Citation; highlighted: boolean }
>(function PassageCard({ chunk, rank, citation, highlighted }, ref) {
  const [expanded, setExpanded] = useState(false);
  const long = chunk.text.length > 300;
  const body = useMemo(
    () => highlight(chunk.text, citation?.quote),
    [chunk.text, citation?.quote],
  );

  const meta = chunk.metadata as {
    kind?: string;
    slide?: number;
    page?: number;
    dataScore?: number;
    hasChart?: boolean;
    hasTable?: boolean;
  };
  const isSlide = meta?.kind === "slide" && typeof meta.slide === "number";
  const locLabel = isSlide
    ? `Slide ${meta.slide}`
    : meta?.kind === "page" && meta.page
      ? `Page ${meta.page}`
      : chunk.heading
        ? `§ ${chunk.heading}`
        : `chunk ${chunk.chunkIndex}`;

  return (
    <article
      ref={ref}
      className={cn(
        "scroll-mt-4 rounded-lg border bg-surface-raised p-3.5 transition-[border-color] duration-200",
        citation ? "border-accent/35" : "border-line/70",
        highlighted && "citation-flash",
      )}
    >
      <div className="flex items-baseline gap-2.5">
        {citation ? (
          <span className="grid h-[1.15rem] min-w-[1.15rem] shrink-0 place-items-center rounded-[5px] bg-accent px-1 font-mono text-[0.62rem] font-semibold text-accent-contrast">
            {citation.marker}
          </span>
        ) : (
          <span
            className="grid h-[1.15rem] w-[1.15rem] shrink-0 place-items-center text-content-muted/60"
            title={`retrieved #${rank}, not cited in the answer`}
          >
            <span className="h-1 w-1 rounded-full bg-current" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.8rem] font-semibold leading-tight text-content-primary">{chunk.title}</p>
          <p className="mt-0.5 flex items-center gap-1.5 truncate text-2xs text-content-muted">
            {isSlide && <PresentationChart className="h-3 w-3 shrink-0 text-accent/70" />}
            {locLabel}
            {isSlide && meta.hasChart && <ChartBar className="h-3 w-3 shrink-0" />}
            {isSlide && meta.hasTable && <Table className="h-3 w-3 shrink-0" />}
            {chunk.category && <span className="text-accent/80">· {chunk.category}</span>}
            {citation && <span className="font-medium text-accent">· cited</span>}
          </p>
        </div>
      </div>

      <p
        className={cn(
          "mt-2.5 whitespace-pre-wrap text-xs leading-relaxed text-content-secondary",
          !expanded && long && "line-clamp-5",
        )}
      >
        {body}
      </p>
      {long && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-2xs text-accent transition-opacity hover:opacity-70"
        >
          {expanded ? "Show less" : "Show full passage"}
        </button>
      )}

      <div className="mt-3 space-y-1.5 border-t border-line/60 pt-2.5">
        <ScoreBar label={isSlide ? "data-rich" : "match"} score={isSlide ? (meta.dataScore ?? 0) : chunk.score} />
        <div className="flex items-center gap-3.5 text-2xs text-content-muted">
          <span>
            vector <span className="tnum text-content-secondary">{scorePercent(chunk.vectorScore)}</span>
          </span>
          <span>
            keyword <span className="tnum text-content-secondary">{scorePercent(chunk.keywordScore)}</span>
          </span>
          <button
            onClick={() =>
              copyToClipboard(
                `> ${chunk.text.slice(0, 400)}\n\n— ${chunk.title}${chunk.heading ? ` (§ ${chunk.heading})` : ""}`,
              ).then((ok) => ok && toast.success("Citation copied"))
            }
            className="ml-auto flex items-center gap-1 text-accent transition-opacity hover:opacity-70"
          >
            <Copy className="h-3 w-3" />
            cite
          </button>
        </div>
      </div>
    </article>
  );
});
