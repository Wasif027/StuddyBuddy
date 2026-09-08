"""Decide *how* to retrieve for a question before retrieving.

* ``pinpoint``  — the default: hybrid search + rerank, a handful of passages.
* ``document``  — the question targets one named material (or "summarise …"):
  load *all* of that document's chunks, in order, and skip ranking.
* ``overview``  — a broad "summarise / key points / tell me about" question with
  no single target: retrieve wide and force diversity across materials.

A named document also tightens ``pinpoint`` — "what does slide deck 3 say about
mitosis?" is scoped to that document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.orm import Document, User

settings = get_settings()

RetrievalMode = Literal["pinpoint", "document", "overview"]

_SUMMARY_RE = re.compile(
    r"\b(summar(y|ise|ize|ising|izing)|overview|recap|gist|tl;?dr|synops(is|e)|"
    r"key (points|takeaways|facts|ideas)|main (points|ideas)|study guide|revise|revision|"
    r"walk me through|brief me|high[- ]level|at a glance|run[- ]?down|"
    r"tell me (about|what)|what('s| is| does).{0,30}(say|cover|contain|in it|about)|"
    r"outline|breakdown|break it down|go over)\b",
    re.IGNORECASE,
)
_WHOLE_DOC_RE = re.compile(
    r"\b(the (whole|entire|full)|this (document|doc|file|deck|slides|chapter|pdf|notes)|"
    r"(document|doc|file|deck|notes) (called|titled|named))\b",
    re.IGNORECASE,
)
_SLIDE_FOCUS_RE = re.compile(
    r"\b(slide|slides|chart|charts|graph|figure|diagram|important|key|interesting|"
    r"highlight|takeaway)\b",
    re.IGNORECASE,
)

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "de",
    "doc", "document", "file", "pdf", "slides", "deck", "notes", "chapter", "please",
    "me", "my", "our", "about", "give", "provide", "show", "tell", "summary", "summarise",
    "summarize", "explain", "version",
}


def _norm(text: str) -> str:
    text = re.sub(r"[_\-/]+", " ", text.lower())
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sig_tokens(text: str) -> list[str]:
    return [t for t in _norm(text).split() if t not in _STOP and len(t) > 1]


@dataclass
class RetrievalPlan:
    mode: RetrievalMode = "pinpoint"
    document_id: str | None = None
    document_title: str | None = None
    k: int = 6
    per_document_cap: int | None = None
    slide_focus: bool = False
    reason: str = "default passage retrieval"


def _match_document(question: str, docs: list[tuple[str, str, str]]) -> tuple[str, str, str] | None:
    """Best (id, title, kind) whose title is clearly referenced in the question."""
    q_norm = _norm(question)
    q_tokens = set(_sig_tokens(question))
    best: tuple[float, str, str, str] | None = None
    for doc_id, title, kind in docs:
        t_norm = _norm(title)
        t_tokens = _sig_tokens(title)
        if not t_tokens:
            continue
        if t_norm and t_norm in q_norm:
            score = 5.0 + len(t_tokens)
        else:
            hit = sum(1 for t in t_tokens if t in q_tokens)
            ratio = hit / len(t_tokens)
            if hit < 2 or ratio < 0.6:
                continue
            score = ratio + hit * 0.1
        if best is None or score > best[0]:
            best = (score, doc_id, title, kind)
    return (best[1], best[2], best[3]) if best else None


def plan_retrieval(
    db: Session,
    user: User,
    question: str,
    top_k: int,
    *,
    document_id: str | None = None,
    intent: str = "auto",
    category_id: str | None = None,
) -> RetrievalPlan:
    base_k = max(top_k, settings.top_k_default)
    docs = list(
        db.execute(
            select(Document.id, Document.title, Document.source_type).where(
                Document.user_id == user.id
            )
        ).all()
    )
    title_by_id = {i: t for i, t, _ in docs}

    if intent == "summary" and document_id and document_id in title_by_id:
        return RetrievalPlan(
            mode="document",
            document_id=document_id,
            document_title=title_by_id[document_id],
            k=settings.document_mode_max_chunks,
            reason=f'full read of "{title_by_id[document_id]}"',
        )
    if document_id and document_id in title_by_id:
        return RetrievalPlan(
            mode="document",
            document_id=document_id,
            document_title=title_by_id[document_id],
            k=settings.document_mode_max_chunks,
            reason=f'full read of "{title_by_id[document_id]}"',
        )

    matched = _match_document(question, docs) if docs else None
    wants_summary = bool(_SUMMARY_RE.search(question))
    whole_doc = bool(_WHOLE_DOC_RE.search(question))

    if matched and (wants_summary or whole_doc):
        return RetrievalPlan(
            mode="document",
            document_id=matched[0],
            document_title=matched[1],
            k=settings.document_mode_max_chunks,
            slide_focus=matched[2] == "pptx" and bool(_SLIDE_FOCUS_RE.search(question)),
            reason=f'full read of "{matched[1]}"',
        )
    if matched:
        return RetrievalPlan(
            mode="pinpoint",
            document_id=matched[0],
            document_title=matched[1],
            k=base_k,
            slide_focus=matched[2] == "pptx" and bool(_SLIDE_FOCUS_RE.search(question)),
            reason=f'passage retrieval scoped to "{matched[1]}"',
        )
    if wants_summary or whole_doc:
        return RetrievalPlan(
            mode="overview",
            k=max(base_k * 2, 12),
            per_document_cap=3,
            reason="broad scan across your materials",
        )
    return RetrievalPlan(mode="pinpoint", k=base_k, reason="default passage retrieval")
