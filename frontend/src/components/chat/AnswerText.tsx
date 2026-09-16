"use client";

import katex from "katex";
import { Fragment, type ReactNode } from "react";

import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Dependency-light renderer for tutor output: paragraphs, `##` headings,
 * `-`/`1.` lists, **bold**, `code`, clickable `[n]` citation markers, and LaTeX
 * maths (`$…$` / `$$…$$` / `\(…\)` / `\[…\]`) via KaTeX.
 */

function renderMath(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex.trim(), {
      displayMode: display,
      throwOnError: false,
      output: "html",
      strict: false,
    });
  } catch {
    return `<code>${tex}</code>`;
  }
}

const _BLOCK_MATH = /^\s*(\$\$|\\\[)([\s\S]*?)(\$\$|\\\])\s*$/;
const _TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/;

function parseTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

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

  for (let idx = 0; idx < lines.length; idx++) {
    const raw = lines[idx];
    const line = raw.trimEnd();
    const blockMath = _BLOCK_MATH.exec(line);
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    const ordered = /^\d+\.\s+(.*)$/.exec(line);
    const isTableStart = line.includes("|") && idx + 1 < lines.length && _TABLE_SEP.test(lines[idx + 1]);

    if (isTableStart) {
      flushList();
      const header = parseTableRow(line);
      const rows: string[][] = [];
      let j = idx + 1; // skip the separator row
      j++;
      while (j < lines.length && lines[j].includes("|") && lines[j].trim()) {
        rows.push(parseTableRow(lines[j]));
        j++;
      }
      blocks.push(
        <div key={`t${blocks.length}`} className="my-2 overflow-x-auto">
          <table>
            <thead>
              <tr>
                {header.map((cell, ci) => (
                  <th key={ci}>{renderInline(cell, byMarker, onCite)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri}>
                  {header.map((_, ci) => (
                    <td key={ci}>{renderInline(row[ci] ?? "", byMarker, onCite)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      idx = j - 1;
      continue;
    }

    if (blockMath) {
      flushList();
      blocks.push(
        <div
          key={`m${blocks.length}`}
          className="my-2 overflow-x-auto text-content-primary"
          dangerouslySetInnerHTML={{ __html: renderMath(blockMath[2], true) }}
        />,
      );
    } else if (heading) {
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
  }
  flushList();

  return (
    <div className="prose-answer">
      {blocks}
      {streaming && <span className="caret" />}
    </div>
  );
}

// split on: [n] markers · **bold** · `code` · $inline$ · \(inline\)
const _INLINE = /(\[\d+\](?:\[\d+\])*|\*\*[^*]+\*\*|`[^`]+`|\$[^$\n]+?\$|\\\([\s\S]*?\\\))/g;

function renderInline(
  text: string,
  byMarker: Map<number, Citation>,
  onCite?: (marker: number) => void,
): ReactNode {
  return text.split(_INLINE).map((part, i) => {
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
    if (/^\$[^$\n]+\$$/.test(part)) {
      return (
        <span key={i} dangerouslySetInnerHTML={{ __html: renderMath(part.slice(1, -1), false) }} />
      );
    }
    if (/^\\\([\s\S]*\\\)$/.test(part)) {
      return (
        <span key={i} dangerouslySetInnerHTML={{ __html: renderMath(part.slice(2, -2), false) }} />
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
