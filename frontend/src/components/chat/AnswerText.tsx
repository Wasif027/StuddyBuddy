"use client";

import { Fragment, type ReactNode } from "react";

import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Dependency-free renderer for answer text: paragraphs, `##` headings,
 * `-`/`1.` lists, **bold**, `code`, and clickable `[n]` citation markers.
 */
export function AnswerText({
  text,
  citations,
  onCite,
  streaming,
}: {
  text: string;
  citations: Citation[];
  onCite?: (marker: number) => void;
  streaming?: boolean;
}) {
  const byMarker = new Map(citations.map((c) => [c.marker, c]));
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={`l${blocks.length}`}>
        {list.items.map((it, i) => (
          <li key={i}>{renderInline(it, byMarker, onCite)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };

  lines.forEach((raw) => {
    const line = raw.trimEnd();
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    const ordered = /^\d+\.\s+(.*)$/.exec(line);

    if (heading) {
      flushList();
      blocks.push(
        <p key={`h${blocks.length}`} className="mt-4 text-[0.8rem] font-semibold uppercase tracking-[0.06em] text-content-secondary">
          {renderInline(heading[2], byMarker, onCite)}
        </p>,
      );
    } else if (bullet) {
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(bullet[1]);
    } else if (ordered) {
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(ordered[1]);
    } else if (!line.trim()) {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={`p${blocks.length}`}>{renderInline(line, byMarker, onCite)}</p>);
    }
  });
  flushList();

  return (
    <div className="prose-answer">
      {blocks}
      {streaming && <span className="caret" />}
    </div>
  );
}

function renderInline(
  text: string,
  byMarker: Map<number, Citation>,
  onCite?: (marker: number) => void,
): ReactNode {
  const parts = text.split(/(\[\d+\](?:\[\d+\])*|\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (/^(\[\d+\])+$/.test(part)) {
      const markers = [...part.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1]));
      return (
        <span key={i} className="mx-0.5 inline-flex gap-px align-[0.08em]">
          {markers.map((marker) => {
            const c = byMarker.get(marker);
            return (
              <button
                key={marker}
                type="button"
                onClick={() => onCite?.(marker)}
                title={c ? `${c.title}${c.quote ? ` — "${c.quote.slice(0, 130)}"` : ""}` : `Source ${marker}`}
                className={cn(
                  "grid h-[1.1rem] min-w-[1.1rem] place-items-center rounded-[4px] px-1 font-mono text-[0.62rem] font-semibold leading-none transition-all duration-150",
                  c
                    ? "bg-accent-soft text-accent hover:bg-accent hover:text-accent-contrast hover:-translate-y-px"
                    : "bg-surface-sunken text-content-muted",
                )}
              >
                {marker}
              </button>
            );
          })}
        </span>
      );
    }
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (/^`[^`]+`$/.test(part)) return <code key={i}>{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}
