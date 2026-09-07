"""RAG + decision orchestration (user- and conversation-scoped).

Pipeline:  resolve chat → persist prompt → embed → hybrid retrieve → rerank →
synthesize (structured) → score confidence → suggest next steps →
persist answer + assistant message → respond.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import tracer
from app.models.orm import (
    Answer,
    Conversation,
    Document,
    Message,
    MessageRole,
    Suggestion,
    SuggestionDecision,
    User,
)
from app.models.schemas import (
    AnalysisBlock,
    AnswerResponse,
    ChartSpec,
    Citation,
    QueryRequest,
    SourceChunk,
    SuggestionRead,
    TokenUsage,
)
from app.services import llm, meta
from app.services.analysis import AnalysisResult, run_analysis
from app.services.embeddings import embed_text
from app.services.query_planner import _ANALYSIS_RE, RetrievalPlan, plan_retrieval
from app.services.reranker import rerank
from app.services.suggestions import to_read as _suggestion_read
from app.services.vectorstore import (
    RetrievedChunk,
    Scope,
    diversify,
    fetch_document_chunks,
    hybrid_search,
)

logger = get_logger(__name__)
settings = get_settings()
_tracer = tracer(__name__)


# --------------------------------------------------------------------- scoring
def _confidence(
    synth_conf: float,
    retrieved: list[RetrievedChunk],
    citations: list[Citation],
    mode: str = "pinpoint",
) -> float:
    if not retrieved:
        return 0.08
    n_citations = len(citations)
    if mode in ("document", "overview"):
        # The evidence is the document (or a wide sample); cosine similarity to a
        # vague "summarise…" query is meaningless here. Lean on the model's own
        # calibrated confidence and whether it actually cited what it was given.
        coverage = min(1.0, n_citations / 3)
        blended = 0.70 * synth_conf + 0.30 * coverage
        return round(max(0.0, min(1.0, blended)), 3)
    # Score the passages the answer actually leaned on, not the top-ranked ones —
    # a clean answer built off rank-2 shouldn't be punished for a noisy rank-1.
    if citations:
        retrieval_conf = sum(c.score for c in citations) / len(citations)
    else:
        retrieval_conf = retrieved[0].score
    coverage = min(1.0, n_citations / 1.5)  # 1 solid citation ≈ 0.67, 2 ≈ 1.0
    blended = 0.40 * synth_conf + 0.45 * retrieval_conf + 0.15 * coverage
    if retrieved[0].score < settings.min_evidence_score:
        blended = min(blended, 0.15)
    return round(max(0.0, min(1.0, blended)), 3)


def _label(conf: float) -> str:
    if conf >= 0.7:
        return "high"
    if conf >= 0.45:
        return "medium"
    if conf >= settings.low_confidence_threshold:
        return "low"
    return "insufficient"


# ---------------------------------------------------------------- conversation
def resolve_conversation(db: Session, user: User, conversation_id: str | None, first_prompt: str) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status_code=404, detail="conversation not found")
        return conv
    title = first_prompt.strip().split("\n", 1)[0][:80] or "New chat"
    conv = Conversation(id=str(uuid.uuid4()), user_id=user.id, title=title)
    db.add(conv)
    db.flush()
    return conv


# --------------------------------------------------------------- conversational
# A follow-up ("and who books it?", "what about the old policy?") carries its
# subject only in the chat history. Fold the recent user turns into the string
# used for *retrieval* (not the displayed question) when the turn looks anaphoric.
_FOLLOWUP_RE = re.compile(
    r"^(and|also|but|so|then|ok(ay)?|what about|how about|what of)\b"
    r"|\b(it|its|it's|that|those|these|this|they|them|there|the same|do so|"
    r"the (former|latter|first|second|one|other))\b",
    re.IGNORECASE,
)


def _recent_turns(db: Session, conv: Conversation, limit: int = 6) -> list[tuple[str, str]]:
    rows = db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc(), Message.role.desc())
        .limit(limit)
    ).all()
    return [(r.value if hasattr(r, "value") else str(r), (c or "").strip()) for r, c in reversed(rows)]


def _contextual_query(question: str, history: list[tuple[str, str]]) -> str:
    if not history or len(question) > 200 or not _FOLLOWUP_RE.search(question.strip()):
        return question
    prior_user = [c for role, c in history if role == "user" and c][-2:]
    if not prior_user:
        return question
    return (" ".join(prior_user) + " " + question).strip()[:600]


def _history_block(history: list[tuple[str, str]], turns: int = 4) -> str | None:
    recent = [(r, c) for r, c in history if c][-turns:]
    if not recent:
        return None
    lines = [f"{'User' if r == 'user' else 'Assistant'}: {c[:400]}" for r, c in recent]
    return "Earlier in this conversation:\n" + "\n".join(lines)


# ------------------------------------------------------------------- planning
def _plan(db: Session, user: User, request: QueryRequest, rq: str) -> RetrievalPlan:
    if request.compare_document_ids:
        return RetrievalPlan(
            mode="pinpoint",
            k=max(request.top_k, settings.top_k_default),
            reason="compare mode — retrieval restricted to the selected documents",
        )
    return plan_retrieval(
        db,
        user,
        rq,
        request.top_k,
        document_id=request.document_id,
        intent=request.intent,
        category_id=request.category_id,
    )


# ------------------------------------------------------------------- retrieval
def _retrieve(
    db: Session, user: User, request: QueryRequest, plan: RetrievalPlan, rq: str
) -> list[RetrievedChunk]:
    with _tracer.start_as_current_span("rag.retrieve") as span:
        span.set_attribute("plan.mode", plan.mode)
        span.set_attribute("plan.reason", plan.reason)
        compare_ids = request.compare_document_ids or None

        # A named document tightens the scope even for a pinpoint question.
        doc_scope = compare_ids or ([plan.document_id] if plan.document_id else None)
        scope = Scope(user_id=user.id, category=request.category_id, document_ids=doc_scope)

        if plan.mode == "document" and plan.document_id:
            results = fetch_document_chunks(db, plan.document_id, scope, plan.k)
        else:
            embedding = embed_text(rq)
            results = hybrid_search(
                db,
                query=rq,
                embedding=embedding,
                k=plan.k + 6,
                candidates=max(settings.retrieval_candidates, plan.k * 4),
                scope=scope,
            )
            results = rerank(rq, results)
            if plan.per_document_cap:
                results = diversify(results, plan.per_document_cap)
            results = results[: plan.k]

        if plan.slide_focus and results:
            results.sort(
                key=lambda r: (r.chunk.metadata_json or {}).get("dataScore", 0.0), reverse=True
            )
        span.set_attribute("results", len(results))
        return results


def _source_chunks(retrieved: list[RetrievedChunk]) -> list[SourceChunk]:
    out: list[SourceChunk] = []
    for r in retrieved:
        c = r.chunk
        out.append(
            SourceChunk(
                chunk_id=c.id,
                document_id=c.document_id,
                title=c.document.title if c.document else c.document_id,
                heading=c.heading,
                chunk_index=c.chunk_index,
                text=c.text,
                category=c.document.category if c.document else None,
                score=round(r.score, 4),
                vector_score=round(r.vector_score, 4),
                keyword_score=round(r.keyword_score, 4),
                rerank_score=round(r.rerank_score, 4) if r.rerank_score is not None else None,
                metadata=c.metadata_json or {},
            )
        )
    return out


_MARKER_RE = re.compile(r"\[(\d+)\]")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-]{2,}")


def _kw(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _splice_markers(
    text: str, uses: list[llm.CitationUse], passages: list[llm.ContextPassage], valid: set[int]
) -> tuple[str, list[int]]:
    """The model returned citations but wrote no [n] tokens — attach each marker
    to the sentence that best matches its quote (or its passage text)."""
    sentences = _SENT_SPLIT.split(text)
    p_by_marker = {p.marker: p for p in passages}
    order: list[int] = []
    for use in uses:
        if use.marker not in valid or use.marker in order:
            continue
        ref = _kw(use.quote or "") or _kw(p_by_marker[use.marker].text)
        best_i, best_ov = len(sentences) - 1, 0
        for i, s in enumerate(sentences):
            ov = len(ref & _kw(s))
            if ov > best_ov:
                best_i, best_ov = i, ov
        sentences[best_i] = sentences[best_i].rstrip()
        if not sentences[best_i].endswith("]"):
            sentences[best_i] += f" [{use.marker}]"
        order.append(use.marker)
    return " ".join(sentences), order


def _normalise_citations(
    answer_text: str,
    uses: list[llm.CitationUse],
    passages: list[llm.ContextPassage],
    retrieved: list[RetrievedChunk],
) -> tuple[str, list[Citation]]:
    """Renumber citation markers to 1..k in order of first appearance in the
    answer, splicing them in when the model forgot to, and dropping stray markers
    that point at nothing. Returns the rewritten answer and the final citations.
    """
    p_by_marker = {p.marker: p for p in passages}
    rc_by_id = {r.chunk.id: r for r in retrieved}
    valid = {u.marker for u in uses if u.marker in p_by_marker}
    if not valid:
        # strip any hallucinated markers so the reader never sees a dead [3]
        return _MARKER_RE.sub("", answer_text).strip(), []

    ordered: list[int] = []
    for m in (int(x) for x in _MARKER_RE.findall(answer_text)):
        if m in valid and m not in ordered:
            ordered.append(m)

    text = answer_text
    if not ordered:
        text, ordered = _splice_markers(text, uses, passages, valid)
    for use in uses:  # any still-missing cited marker → append at the end
        if use.marker in valid and use.marker not in ordered:
            ordered.append(use.marker)
            text = f"{text.rstrip()} [{use.marker}]"

    remap = {old: i + 1 for i, old in enumerate(ordered)}
    text = _MARKER_RE.sub(
        lambda mo: f"[{remap[int(mo.group(1))]}]" if int(mo.group(1)) in remap else "", text
    ).strip()

    quote_by_marker = {u.marker: u.quote for u in uses}
    cites: list[Citation] = []
    for old in ordered:
        p = p_by_marker[old]
        rc = rc_by_id.get(p.chunk_id)
        quote = (quote_by_marker.get(old) or "").strip() or p.text[:240]
        cites.append(
            Citation(
                marker=remap[old],
                chunk_id=p.chunk_id,
                document_id=rc.chunk.document_id if rc else "",
                title=p.title,
                category=rc.chunk.document.category if rc and rc.chunk.document else None,
                page=None,
                quote=quote[:600],
                score=round(rc.score if rc else p.score, 4),
            )
        )
    return text, cites


def _has_strong_citation(citations: list[Citation]) -> bool:
    floor = settings.min_evidence_score * 3
    return any(c.score >= floor for c in citations)


def _passages(retrieved: list[RetrievedChunk]) -> list[llm.ContextPassage]:
    return [
        llm.ContextPassage(
            marker=i + 1,
            chunk_id=r.chunk.id,
            title=r.chunk.document.title if r.chunk.document else r.chunk.document_id,
            heading=r.chunk.heading,
            text=r.chunk.text,
            score=r.score,
        )
        for i, r in enumerate(retrieved)
    ]


# ---------------------------------------------------------------- suggestions
def _persist_suggestions(
    db: Session,
    user: User,
    answer_id: str,
    conv: Conversation,
    message_id: str,
    question: str,
    answer_text: str,
    passages: list[llm.ContextPassage],
    enable: bool,
) -> list[SuggestionRead]:
    if not enable or not settings.suggestions_enabled:
        return []
    with _tracer.start_as_current_span("rag.suggest") as span:
        steps = llm.suggest_actions(question, answer_text, passages)
        span.set_attribute("steps", len(steps))
        rows: list[Suggestion] = []
        for s in steps:
            row = Suggestion(
                id=str(uuid.uuid4()),
                user_id=user.id,
                answer_id=answer_id,
                conversation_id=conv.id,
                message_id=message_id,
                question=question,
                text=s.text,
                rationale=s.rationale or None,
                priority=s.priority,
                kind=s.kind,
                decision=SuggestionDecision.PENDING,
            )
            db.add(row)
            rows.append(row)
        if rows:
            db.flush()
        return [_suggestion_read(r) for r in rows]


# ------------------------------------------------------------------- assemble
def _assemble(
    db: Session,
    user: User,
    conv: Conversation,
    request: QueryRequest,
    retrieved: list[RetrievedChunk],
    synth: llm.Synthesis,
    passages: list[llm.ContextPassage],
    latency_ms: float,
    plan: RetrievalPlan,
) -> AnswerResponse:
    answer_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    compare = bool(request.compare_document_ids)
    source_chunks = _source_chunks(retrieved)

    answer_text = synth.answer.strip()
    answer_text, citations = _normalise_citations(answer_text, synth.citations, passages, retrieved)
    confidence = _confidence(synth.confidence, retrieved, citations, plan.mode)
    label = _label(confidence)
    if plan.mode in ("document", "overview"):
        insufficient = not retrieved
    else:
        # A borderline model confidence alone no longer flips the verdict — if the
        # answer cites a passage that genuinely matched, treat it as sufficient.
        insufficient = (not retrieved) or (
            label == "insufficient" and not _has_strong_citation(citations)
        )

    if insufficient:
        low = answer_text.lower()
        model_gave_up = (not answer_text) or low.startswith(
            ("i could not", "i couldn't", "i don't", "i do not", "the provided passages",
             "the passages do not", "there is no", "no information", "i cannot", "i can't")
        )
        if model_gave_up:
            answer_text = _insufficient_message(db, user, request.question)
            citations = []
        else:
            answer_text = (
                "Note: your documents have limited evidence for this — treat the following as "
                "low-confidence.\n\n" + answer_text
            )

    db.add(
        Answer(
            id=answer_id,
            user_id=user.id,
            conversation_id=conv.id,
            question=request.question,
            answer=answer_text,
            confidence=confidence,
            model=synth.model,
            category_id=request.category_id,
            compare_mode=compare,
            latency_ms=latency_ms,
            citations_json=[c.model_dump(by_alias=True) for c in citations],
            source_chunks_json=[s.model_dump(by_alias=True) for s in source_chunks],
            follow_ups_json=synth.follow_ups,
            usage_json=synth.usage or {},
        )
    )
    db.flush()

    # No point asking the model for "next steps" on an answer we couldn't ground.
    suggestions = _persist_suggestions(
        db, user, answer_id, conv, message_id, request.question, answer_text, passages,
        request.suggest and not insufficient,
    )

    response = AnswerResponse(
        id=answer_id,
        conversation_id=conv.id,
        message_id=message_id,
        question=request.question,
        answer=answer_text,
        confidence=confidence,
        confidence_label=label,  # type: ignore[arg-type]
        insufficient_evidence=insufficient,
        compare_mode=compare,
        retrieval_mode=plan.mode,
        retrieval_note=plan.reason,
        citations=citations,
        source_chunks=source_chunks,
        suggestions=suggestions,
        follow_ups=synth.follow_ups,
        model=synth.model,
        provider=synth.provider,
        latency_ms=round(latency_ms, 2),
        usage=TokenUsage(**{k: synth.usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens")}),
        cached=False,
        created_at=datetime.now(UTC),
    )

    db.add(
        Message(
            id=message_id,
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            answer_json=response.model_dump(by_alias=True, mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    conv.updated_at = datetime.now(UTC)
    db.commit()
    return response


def _analysis_should_fall_back(result: AnalysisResult, request: QueryRequest) -> bool:
    """The planner guessed 'analysis' but the model can't answer from the sheet —
    unless the user explicitly asked for analysis, retry as normal retrieval."""
    if request.intent == "analysis":
        return False
    return not result.ok and result.error in ("no query", "no spreadsheet data in scope")


def _ctx_passages(chunks: list[RetrievedChunk]) -> list[llm.ContextPassage]:
    return [
        llm.ContextPassage(
            marker=i + 1,
            chunk_id=h.chunk.id,
            title=h.chunk.document.title if h.chunk.document else "",
            heading=h.chunk.heading,
            text=h.chunk.text,
            score=h.score,
        )
        for i, h in enumerate(chunks)
    ]


def _assemble_analysis(
    db: Session,
    user: User,
    conv: Conversation,
    request: QueryRequest,
    plan: RetrievalPlan,
    result: AnalysisResult,
    latency_ms: float,
) -> AnswerResponse:
    answer_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    context = result.context_chunks
    source_chunks = _source_chunks(context)
    ctx_passages = _ctx_passages(context)
    synth = result.narrative or llm.Synthesis(answer="", citations=[], confidence=0.3)

    if result.ok:
        confidence = round(min(1.0, 0.5 + 0.45 * synth.confidence), 3)
        raw_answer = synth.answer.strip() or "See the computed result."
        answer_text, citations = _normalise_citations(
            raw_answer, synth.citations, ctx_passages, context
        )
        block = AnalysisBlock(
            ok=True,
            sql=result.sql,
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
            truncated=result.truncated,
            tables_used=result.tables_used,
            assumptions=result.assumptions,
            chart=ChartSpec(**result.chart) if result.chart else None,
        )
        insufficient = False
    else:
        confidence = 0.2
        citations = []
        answer_text = "I couldn't compute this from the spreadsheet data — " + (
            result.error or "the query could not be built"
        )
        if result.assumptions:
            answer_text += f"\n\n{result.assumptions}"
        block = AnalysisBlock(ok=False, error=result.error, assumptions=result.assumptions)
        insufficient = True

    label = _label(confidence)
    model_name = synth.model or settings.active_model_name
    db.add(
        Answer(
            id=answer_id,
            user_id=user.id,
            conversation_id=conv.id,
            question=request.question,
            answer=answer_text,
            confidence=confidence,
            model=model_name,
            category_id=request.category_id,
            compare_mode=False,
            latency_ms=latency_ms,
            citations_json=[c.model_dump(by_alias=True) for c in citations],
            source_chunks_json=[s.model_dump(by_alias=True) for s in source_chunks],
            follow_ups_json=synth.follow_ups,
            usage_json={"analysis": True},
        )
    )
    db.flush()

    suggestions = _persist_suggestions(
        db, user, answer_id, conv, message_id, request.question, answer_text, ctx_passages,
        request.suggest and result.ok,
    )

    response = AnswerResponse(
        id=answer_id,
        conversation_id=conv.id,
        message_id=message_id,
        question=request.question,
        answer=answer_text,
        confidence=confidence,
        confidence_label=label,  # type: ignore[arg-type]
        insufficient_evidence=insufficient,
        compare_mode=False,
        retrieval_mode="analysis",
        retrieval_note=plan.reason,
        analysis=block,
        citations=citations,
        source_chunks=source_chunks,
        suggestions=suggestions,
        follow_ups=synth.follow_ups,
        model=model_name,
        provider=synth.provider or settings.llm_provider,
        latency_ms=round(latency_ms, 2),
        usage=TokenUsage(),
        cached=False,
        created_at=datetime.now(UTC),
    )

    db.add(
        Message(
            id=message_id,
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            answer_json=response.model_dump(by_alias=True, mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    conv.updated_at = datetime.now(UTC)
    db.commit()
    return response


# --------------------------------------------------------------------- meta
def _user_doc_count(db: Session, user: User) -> int:
    return int(
        db.execute(
            select(func.count(Document.id)).where(Document.user_id == user.id)
        ).scalar_one()
    )


def _user_categories(db: Session, user: User) -> list[str]:
    rows = db.execute(
        select(Document.category).where(Document.user_id == user.id).distinct()
    ).scalars().all()
    return sorted({(c or "uncategorized") for c in rows})


def _user_has_sheet(db: Session, user: User) -> bool:
    return db.execute(
        select(Document.id).where(
            Document.user_id == user.id, Document.source_type.in_(("xlsx", "xls"))
        ).limit(1)
    ).first() is not None


def _insufficient_message(db: Session, user: User, question: str) -> str:
    if _user_doc_count(db, user) == 0:
        return (
            "You haven't added any documents yet, so there's nothing for me to search. "
            "Click **Add document** to upload a PDF, Word doc, spreadsheet or slide deck — "
            "then ask about it."
        )
    if bool(_ANALYSIS_RE.search(question)) and not _user_has_sheet(db, user):
        return (
            "This looks like a data question, but you haven't uploaded a spreadsheet with "
            "that data. Add the `.xlsx` and ask again."
        )
    cats = _user_categories(db, user)
    label = {
        "policy": "Policies", "contract": "Contracts", "runbook": "Runbooks",
        "tech-doc": "Technical Docs", "meeting-notes": "Meeting Notes", "incident": "Incidents",
        "hr": "HR", "finance": "Finance", "legal": "Legal", "security": "Security",
        "sales": "Sales", "data": "Data & Reports", "deck": "Decks",
        "uncategorized": "Uncategorised",
    }
    cat_str = ", ".join(label.get(c, c.replace("-", " ").title()) for c in cats)
    return (
        f"I couldn't find anything about that in your documents. You have: {cat_str}. "
        "Try rephrasing, or add a document that covers it."
    )


def _meta_answer_response(request: QueryRequest, conv_id: str | None, msg_id: str | None, text: str) -> AnswerResponse:
    return AnswerResponse(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        message_id=msg_id,
        question=request.question,
        answer=text,
        confidence=1.0,
        confidence_label="high",  # type: ignore[arg-type]
        insufficient_evidence=False,
        compare_mode=False,
        retrieval_mode="meta",
        retrieval_note="answered from your library",
        model="assistant",
        provider="assistant",
        latency_ms=0.0,
        cached=False,
        created_at=datetime.now(UTC),
    )


def _persist_meta(db: Session, conv: Conversation, request: QueryRequest, text: str) -> AnswerResponse:
    """Meta answer inside an existing chat — save the turn, no Answer/Suggestion rows."""
    message_id = str(uuid.uuid4())
    response = _meta_answer_response(request, conv.id, message_id, text)
    db.add(
        Message(
            id=message_id,
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=text,
            answer_json=response.model_dump(by_alias=True, mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    conv.updated_at = datetime.now(UTC)
    db.commit()
    return response


def _cache_key(user: User, request: QueryRequest) -> str:
    return cache.cache_key(
        "answer",
        user.id,
        request.question.strip().lower(),
        request.top_k,
        request.category_id or "",
        request.document_id or "",
        request.intent,
        request.conversation_id or "",
        sorted(request.compare_document_ids or []),
        request.suggest,
        settings.active_model_name,
    )


# --------------------------------------------------------------------- public
def generate_answer(db: Session, user: User, request: QueryRequest) -> AnswerResponse:
    started = time.perf_counter()
    with _tracer.start_as_current_span("rag.generate_answer") as span:
        span.set_attribute("question.length", len(request.question))

        meta_kind = meta.detect(request.question)
        # A real question with an empty library gets a "add a document" reply
        # instead of running the whole pipeline for nothing.
        meta_text = (
            meta.answer(db, user, meta_kind) if meta_kind
            else (_insufficient_message(db, user, request.question)
                  if _user_doc_count(db, user) == 0 else None)
        )
        if meta_text is not None:
            span.set_attribute("meta", meta_kind or "no_docs")
            ephemeral = request.conversation_id is None and (
                meta_kind is None or meta.is_ephemeral(meta_kind)
            )
            if ephemeral:
                return _meta_answer_response(request, None, None, meta_text)
            conv = resolve_conversation(db, user, request.conversation_id, request.question)
            db.add(
                Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=MessageRole.USER,
                        content=request.question, created_at=datetime.now(UTC))
            )
            return _persist_meta(db, conv, request, meta_text)

        conv = resolve_conversation(db, user, request.conversation_id, request.question)
        history = _recent_turns(db, conv)
        db.add(
            Message(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                role=MessageRole.USER,
                content=request.question,
                created_at=datetime.now(UTC),
            )
        )

        key = _cache_key(user, request)
        if not request.bypass_cache:
            hit = cache.get_json(key)
            if hit:
                span.set_attribute("cache.hit", True)
                hit["cached"] = True
                hit["conversationId"] = conv.id
                cached = AnswerResponse.model_validate(hit)
                msg = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conv.id,
                    role=MessageRole.ASSISTANT,
                    content=cached.answer,
                    answer_json=hit,
                    created_at=datetime.now(UTC),
                )
                db.add(msg)
                conv.updated_at = datetime.now(UTC)
                db.commit()
                cached.message_id = msg.id
                return cached

        rq = _contextual_query(request.question, history)
        plan = _plan(db, user, request, rq)
        span.set_attribute("plan.mode", plan.mode)

        if plan.mode == "analysis":
            result = run_analysis(
                db,
                user,
                question=request.question,
                primary_document_id=plan.document_id,
                scope_document_ids=request.compare_document_ids,
                history=_history_block(history),
            )
            if _analysis_should_fall_back(result, request):
                plan = RetrievalPlan(mode="pinpoint", k=max(request.top_k, settings.top_k_default),
                                     reason="passage retrieval (the question isn't answerable from the sheet)")
            else:
                latency_ms = (time.perf_counter() - started) * 1000
                response = _assemble_analysis(db, user, conv, request, plan, result, latency_ms)
                if result.ok and not response.suggestions:
                    cache.set_json(key, response.model_dump(by_alias=True))
                span.set_attribute("confidence", response.confidence)
                return response

        retrieved = _retrieve(db, user, request, plan, rq)
        passages = _passages(retrieved)
        synth = llm.synthesize(
            request.question,
            passages,
            compare=bool(request.compare_document_ids),
            mode=plan.mode,
            history=_history_block(history),
        )
        latency_ms = (time.perf_counter() - started) * 1000
        response = _assemble(db, user, conv, request, retrieved, synth, passages, latency_ms, plan)

        if not response.insufficient_evidence and not response.suggestions:
            cache.set_json(key, response.model_dump(by_alias=True))
        span.set_attribute("confidence", response.confidence)
        return response


async def stream_answer(db: Session, user: User, request: QueryRequest) -> AsyncIterator[dict]:
    """Yield SSE frames: start → grounding → [analysis] → token* → [suggestions] → final."""
    started = time.perf_counter()

    meta_kind = meta.detect(request.question)
    meta_text = (
        meta.answer(db, user, meta_kind) if meta_kind
        else (_insufficient_message(db, user, request.question)
              if _user_doc_count(db, user) == 0 else None)
    )
    if meta_text is not None:
        ephemeral = request.conversation_id is None and (
            meta_kind is None or meta.is_ephemeral(meta_kind)
        )
        if ephemeral:
            response = _meta_answer_response(request, None, None, meta_text)
            yield {"type": "start", "payload": {"question": request.question, "conversationId": ""}}
        else:
            conv = resolve_conversation(db, user, request.conversation_id, request.question)
            db.add(
                Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=MessageRole.USER,
                        content=request.question, created_at=datetime.now(UTC))
            )
            db.flush()
            yield {"type": "start", "payload": {"question": request.question, "conversationId": conv.id}}
            response = _persist_meta(db, conv, request, meta_text)
        for i, w in enumerate(meta_text.split(" ")):
            yield {"type": "token", "payload": {"text": (" " if i else "") + w}}
        yield {"type": "final", "payload": response.model_dump(by_alias=True, mode="json")}
        return

    conv = resolve_conversation(db, user, request.conversation_id, request.question)
    history = _recent_turns(db, conv)
    db.add(
        Message(
            id=str(uuid.uuid4()),
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=request.question,
            created_at=datetime.now(UTC),
        )
    )
    db.flush()
    yield {"type": "start", "payload": {"question": request.question, "conversationId": conv.id}}

    rq = _contextual_query(request.question, history)
    plan = _plan(db, user, request, rq)

    if plan.mode == "analysis":
        result = run_analysis(
            db,
            user,
            question=request.question,
            primary_document_id=plan.document_id,
            scope_document_ids=request.compare_document_ids,
            history=_history_block(history),
        )
        if _analysis_should_fall_back(result, request):
            plan = RetrievalPlan(mode="pinpoint", k=max(request.top_k, settings.top_k_default),
                                 reason="passage retrieval (the question isn't answerable from the sheet)")
        else:
            latency_ms = (time.perf_counter() - started) * 1000
            response = _assemble_analysis(db, user, conv, request, plan, result, latency_ms)
            yield {
                "type": "grounding",
                "payload": {
                    "sourceChunks": [s.model_dump(by_alias=True) for s in response.source_chunks],
                    "retrievalMode": "analysis",
                    "retrievalNote": plan.reason,
                },
            }
            if response.analysis is not None:
                yield {"type": "analysis", "payload": response.analysis.model_dump(by_alias=True)}
            for i, w in enumerate(response.answer.split(" ")):
                yield {"type": "token", "payload": {"text": (" " if i else "") + w}}
            if response.suggestions:
                yield {
                    "type": "suggestions",
                    "payload": {"suggestions": [s.model_dump(by_alias=True) for s in response.suggestions]},
                }
            yield {"type": "final", "payload": response.model_dump(by_alias=True, mode="json")}
            return

    retrieved = _retrieve(db, user, request, plan, rq)
    passages = _passages(retrieved)
    source_chunks = _source_chunks(retrieved)
    yield {
        "type": "grounding",
        "payload": {
            "sourceChunks": [s.model_dump(by_alias=True) for s in source_chunks],
            "retrievalMode": plan.mode,
            "retrievalNote": plan.reason,
        },
    }

    synth = llm.synthesize(
        request.question,
        passages,
        compare=bool(request.compare_document_ids),
        mode=plan.mode,
        history=_history_block(history),
    )

    buf = ""
    words = synth.answer.split(" ")
    for i, w in enumerate(words):
        buf += (" " if i else "") + w
        if len(buf) >= 18 or i == len(words) - 1:
            yield {"type": "token", "payload": {"text": buf}}
            buf = ""

    latency_ms = (time.perf_counter() - started) * 1000
    response = _assemble(db, user, conv, request, retrieved, synth, passages, latency_ms, plan)

    if response.suggestions:
        yield {
            "type": "suggestions",
            "payload": {"suggestions": [s.model_dump(by_alias=True) for s in response.suggestions]},
        }
    if not response.insufficient_evidence and not response.suggestions and not request.bypass_cache:
        cache.set_json(_cache_key(user, request), response.model_dump(by_alias=True))

    yield {"type": "final", "payload": response.model_dump(by_alias=True, mode="json")}


def count_message_count(db: Session, conversation_id: str) -> int:
    return int(
        db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        ).scalar_one()
    )
