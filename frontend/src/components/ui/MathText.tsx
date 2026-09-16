"use client";

import katex from "katex";
import { Fragment, type ReactNode } from "react";

/**
 * Lightweight inline renderer for model output outside the chat (practice
 * questions, feedback, answer keys): **bold**, `code`, line breaks, and LaTeX
 * maths — `$…$` / `$$…$$` inline and a lone `$$…$$` / `\[…\]` line as a block.
 * The chat uses {@link AnswerText}, which adds citation markers on top of this.
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
    return tex;
  }
}

const _BLOCK_MATH = /^\s*(\$\$|\\\[)([\s\S]*?)(\$\$|\\\])\s*$/;
// split on: **bold** · `code` · $$inline$$ · $inline$ · \(inline\)
const _INLINE =
  /(\*\*[^*\n]+\*\*|`[^`\n]+`|\$\$[^$\n]+?\$\$|\$[^$\n]+?\$|\\\([\s\S]*?\\\))/g;

function renderInline(text: string): ReactNode[] {
  return text.split(_INLINE).map((part, i) => {
    if (/^\*\*[^*\n]+\*\*$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (/^`[^`\n]+`$/.test(part)) return <code key={i}>{part.slice(1, -1)}</code>;
    if (/^\$\$[^$\n]+\$\$$/.test(part))
      return <span key={i} dangerouslySetInnerHTML={{ __html: renderMath(part.slice(2, -2), false) }} />;
    if (/^\$[^$\n]+\$$/.test(part))
      return <span key={i} dangerouslySetInnerHTML={{ __html: renderMath(part.slice(1, -1), false) }} />;
    if (/^\\\([\s\S]*\\\)$/.test(part))
      return <span key={i} dangerouslySetInnerHTML={{ __html: renderMath(part.slice(2, -2), false) }} />;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function MathText({ text, className }: { text: string | null | undefined; className?: string }) {
  const lines = (text ?? "").replace(/\r\n/g, "\n").split("\n");
  return (
    <span className={className}>
      {lines.map((line, i) => {
        const block = _BLOCK_MATH.exec(line);
        return (
          <Fragment key={i}>
            {i > 0 && <br />}
            {block ? (
              <span
                className="block my-1 overflow-x-auto"
                dangerouslySetInnerHTML={{ __html: renderMath(block[2], true) }}
              />
            ) : (
              renderInline(line)
            )}
          </Fragment>
        );
      })}
    </span>
  );
}
