"""Decide *how* to retrieve for a question before retrieving.

Naive passage retrieval answers "what is the re-delivery fee?" well but fails
"summarise the driver handbook" or "which product sold at a loss". This module
classifies the question and picks a strategy:

* ``pinpoint``  — the default: hybrid search + rerank, a handful of passages.
* ``document``  — the question targets one named document (optionally "summarise
  …"): load *all* of that document's chunks, in order, and skip ranking.
* ``overview``  — a broad "summarise / key points / tell me about" question with
  no single target: retrieve wide and force diversity across documents.
* ``analysis`` — an analytic question over uploaded spreadsheet data: hand off to
  text-to-SQL (``services.analysis``) instead of passage retrieval.

A named document also tightens ``pinpoint`` — "what does the BrightMart
agreement say about liability?" is scoped to that document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.orm import Document, User
from app.services.llm import classify_query

settings = get_settings()

RetrievalMode = Literal["pinpoint", "document", "overview", "analysis"]

_SHEET_KINDS = {"xlsx", "xls"}

# "give me the gist", "walk me through", "what's in this doc", "key points" …
_SUMMARY_RE = re.compile(
    r"\b(summar(y|ise|ize|ising|izing)|overview|recap|gist|tl;?dr|synops(is|e)|"
    r"key (points|takeaways|facts)|main (points|ideas)|"
    r"walk me through|brief me|high[- ]level|at a glance|run[- ]?down|"
    r"tell me (about|what)|what('s| is| does).{0,30}(say|cover|contain|in it|about)|"
    r"outline|breakdown|break it down)\b",
    re.IGNORECASE,
)
_WHOLE_DOC_RE = re.compile(
    r"\b(the (whole|entire|full)|this (document|doc|file|policy|contract|report|handbook)|"
    r"the (document|doc|file) (called|titled|named))\b",
    re.IGNORECASE,
)
# analytic intent — computation / aggregation / ranking over records
_ANALYSIS_RE = re.compile(
    r"\b(calculate|compute|how many|how much|number of|count|total|sum|subtotal|average|"
    r"avg|mean|median|min(imum)?|max(imum)?|most|least|highest|lowest|top\s+\d+|bottom\s+\d+|"
    r"rank|ranking|per\s+\w+|by\s+(month|region|product|category|customer|quarter|year|week|day)|"
    r"breakdown by|group(ed)? by|at a loss|loss-?making|unprofitable|profit|margin|revenue|"
    r"turnover|sales|units? sold|quantity|trend|growth|decline|year[- ]over[- ]year|"
    r"month[- ]over[- ]month|yoy|mom|% ?(change|of)|percentage|share of|outlier|anomal|"
    r"which (product|customer|region|order|month|item|sku|category)|what (was|were|is) the total)\b",
    re.IGNORECASE,
)
_SLIDE_FOCUS_RE = re.compile(
    r"\b(slide|slides|chart|charts|graph|figure|data|numbers?|important|key|interesting|"
    r"highlight|takeaway)\b",
    re.IGNORECASE,
)

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "de",
    "doc", "document", "file", "pdf", "xlsx", "sheet", "spreadsheet", "deck", "please",
    "me", "my", "our", "about", "give", "provide", "show", "tell", "summary", "summarise",
    "summarize", "version", "data",
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
    if best is None:
        return None
    return best[1], best[2], best[3]


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
    kind_by_id = {i: k for i, _, k in docs}
    title_by_id = {i: t for i, t, _ in docs}
    sheets_in_scope = [
        (i, t) for i, t, k in docs if k in _SHEET_KINDS and (not category_id)
    ]
    # (category scoping of sheets is by the caller's Scope; here we only need to
    #  know whether *a* spreadsheet is reachable for an analytic question)
    all_sheets = [(i, t) for i, t, k in docs if k in _SHEET_KINDS]

    # ---- explicit intent from the UI ----------------------------------------
    if intent == "analysis":
        target = document_id or (all_sheets[0][0] if all_sheets else None)
        if target and kind_by_id.get(target) in _SHEET_KINDS:
            return RetrievalPlan(
                mode="analysis",
                document_id=target,
                document_title=title_by_id.get(target),
                reason=f'computed from "{title_by_id.get(target, target)}"',
            )
    if intent == "summary" and document_id and document_id in title_by_id:
        return RetrievalPlan(
            mode="document",
            document_id=document_id,
            document_title=title_by_id[document_id],
            k=settings.document_mode_max_chunks,
            reason=f'full-document read of "{title_by_id[document_id]}"',
        )
    if document_id and document_id in title_by_id:
        title = title_by_id[document_id]
        return RetrievalPlan(
            mode="document",
            document_id=document_id,
            document_title=title,
            k=settings.document_mode_max_chunks,
            reason=f'full-document read of "{title}"',
        )

    matched = _match_document(question, docs) if docs else None
    wants_summary = bool(_SUMMARY_RE.search(question))
    whole_doc = bool(_WHOLE_DOC_RE.search(question))
    analytic = bool(_ANALYSIS_RE.search(question))
    reachable = sheets_in_scope or all_sheets

    # ---- ambiguous phrasing / typos: ask the model what they meant --------
    # Only when the fast heuristics gave no signal AND a spreadsheet is around
    # (so a mis-worded "waht sells best" still reaches the analytics path).
    if reachable and not analytic and not matched and not wants_summary and not whole_doc:
        kind = classify_query(question)
        if kind == "analysis":
            analytic = True
        elif kind == "summary":
            wants_summary = True

    # ---- analytic question + at least one spreadsheet is reachable --------
    # If the question names a sheet, target it; otherwise leave document_id None
    # and let run_analysis register every spreadsheet in scope (it can JOIN
    # across them). If the model then can't build a query, rag falls back to
    # normal retrieval — so over-routing here is safe.
    if analytic and reachable:
        if matched and matched[2] in _SHEET_KINDS:
            target_id = matched[0]
            title = title_by_id.get(target_id, target_id)
            reason = f'computed from "{title}"'
        else:
            target_id = None
            title = None
            reason = (
                f'computed from "{reachable[0][1]}"'
                if len(reachable) == 1
                else "computed from your spreadsheet data"
            )
        return RetrievalPlan(
            mode="analysis",
            document_id=target_id,
            document_title=title,
            reason=reason,
        )

    if matched and (wants_summary or whole_doc):
        return RetrievalPlan(
            mode="document",
            document_id=matched[0],
            document_title=matched[1],
            k=settings.document_mode_max_chunks,
            slide_focus=matched[2] == "pptx" and bool(_SLIDE_FOCUS_RE.search(question)),
            reason=f'full-document read of "{matched[1]}"',
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
            reason="broad scan across the knowledge base",
        )
    return RetrievalPlan(mode="pinpoint", k=base_k, reason="default passage retrieval")
