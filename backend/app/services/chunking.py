"""Structure-aware text chunking.

Splits on blank lines / Markdown headings first, then packs paragraphs into
token-bounded windows with a sentence-level overlap. Each chunk keeps the most
recent heading so citations and the grounding panel can show useful context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token, min 1 per word)."""
    words = len(text.split())
    return max(words, len(text) // 4)


@dataclass
class Chunk:
    index: int
    text: str
    heading: str | None = None
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


def _blocks(text: str) -> list[tuple[str | None, str]]:
    """Yield (heading, paragraph) pairs, tracking the current heading."""
    out: list[tuple[str | None, str]] = []
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if buf:
            para = "\n".join(buf).strip()
            if para:
                out.append((heading, para))
            buf = []

    for line in text.replace("\r\n", "\n").split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            flush()
            heading = m.group(2).strip()
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return out


def _overlap_tail(text: str, max_tokens: int) -> str:
    tail: list[str] = []
    total = 0
    for s in reversed(_SENT_RE.split(text)):
        t = estimate_tokens(s)
        if total + t > max_tokens and tail:
            break
        tail.insert(0, s)
        total += t
    return " ".join(tail).strip()


def _split_paragraph(para: str, max_tokens: int) -> list[str]:
    """Split a paragraph on sentence boundaries only if it exceeds max_tokens."""
    if estimate_tokens(para) <= max_tokens:
        return [para]
    out: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for sent in _SENT_RE.split(para):
        st = estimate_tokens(sent)
        if buf and buf_tokens + st > max_tokens:
            out.append(" ".join(buf))
            buf, buf_tokens = [], 0
        buf.append(sent)
        buf_tokens += st
    if buf:
        out.append(" ".join(buf))
    return out


def chunk_text(
    text: str,
    *,
    target_tokens: int = 320,
    max_tokens: int = 420,
    overlap_tokens: int = 60,
) -> list[Chunk]:
    """Group paragraphs into token-bounded chunks, one heading per chunk.

    Overlap is applied only between consecutive chunks *within the same
    heading* (i.e. when a long section is split), never across a heading
    boundary — so a chunk's text always belongs to its labelled section.
    """
    text = (text or "").strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    cur: list[str] = []
    cur_tokens = 0
    cur_heading: str | None = None

    def flush(carry_overlap: bool) -> None:
        nonlocal cur, cur_tokens
        body = "\n\n".join(cur).strip()
        cur, cur_tokens = [], 0
        if not body:
            return
        prev = chunks[-1] if chunks else None
        if carry_overlap and prev is not None and prev.heading == cur_heading:
            tail = _overlap_tail(prev.text, overlap_tokens)
            if tail and tail not in body:
                body = f"{tail} {body}".strip()
        chunks.append(
            Chunk(index=len(chunks), text=body, heading=cur_heading, token_count=estimate_tokens(body))
        )

    for heading, para in _blocks(text):
        if cur and heading != cur_heading:
            flush(carry_overlap=False)
        cur_heading = heading
        for piece in _split_paragraph(para, max_tokens):
            pt = estimate_tokens(piece)
            if cur and cur_tokens + pt > max_tokens:
                flush(carry_overlap=True)
            cur.append(piece)
            cur_tokens += pt
            if cur_tokens >= target_tokens:
                flush(carry_overlap=True)

    flush(carry_overlap=True)
    return chunks
