"""Tutor RAG orchestration (user- and conversation-scoped).

Pipeline:  resolve chat → persist prompt → embed → hybrid retrieve → rerank →
explain (grounded, at the right depth) → score confidence → persist answer +
assistant message → respond.  JSON and SSE variants.
"""

from __future__ import annotations

import re
import threading
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
from app.models.orm import Answer, Category, Conversation, Document, Message, MessageRole, User
from app.models.schemas import AnswerResponse, Citation, QueryRequest, SourceChunk, TokenUsage
from app.services import llm, meta
from app.services.embeddings import embed_text
from app.services.query_planner import RetrievalPlan, plan_retrieval
from app.services.reranker import rerank
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

_LEVELS = ("simple", "standard", "deep", "exam")


# --------------------------------------------------------------------- scoring
def _confidence(
    synth_conf: float,
    retrieved: list[RetrievedChunk],
    citations: list[Citation],
    mode: str = "pinpoint",
) -> float:
    if not retrieved:
        return round(max(0.0, min(1.0, synth_conf)), 3)
    n = len(citations)
    if mode in ("document", "overview"):
        coverage = min(1.0, n / 3)
        return round(max(0.0, min(1.0, 0.70 * synth_conf + 0.30 * coverage)), 3)
    retrieval_conf = (sum(c.score for c in citations) / n) if citations else retrieved[0].score
    coverage = min(1.0, n / 1.5)
    blended = 0.40 * synth_conf + 0.45 * retrieval_conf + 0.15 * coverage
    if retrieved[0].score < settings.min_evidence_score:
        blended = min(blended, 0.25)
    return round(max(0.0, min(1.0, blended)), 3)


def _label(conf: float) -> str:
    if conf >= 0.7:
        return "high"
    if conf >= 0.45:
        return "medium"
    if conf >= settings.low_confidence_threshold:
        return "low"
    return "insufficient"


# ------------------------------------------------------------------- level
def _resolve_level(db: Session, user: User, request: QueryRequest) -> str:
    if request.explain_level in _LEVELS:
        return request.explain_level  # type: ignore[return-value]
    if request.category_id:
        cat = db.execute(
            select(Category).where(
                Category.user_id == user.id, Category.slug == request.category_id
            )
        ).scalar_one_or_none()
        if cat and cat.level in _LEVELS:
            return cat.level
    return settings.default_explain_level


def _student_level(db: Session, user: User, request: QueryRequest) -> str:
    if request.category_id:
        cat = db.execute(
            select(Category).where(
                Category.user_id == user.id, Category.slug == request.category_id
            )
        ).scalar_one_or_none()
        if cat and cat.level:
            return cat.level
    return user.study_level or settings.default_study_level


# ---------------------------------------------------------------- conversation
def resolve_conversation(
    db: Session, user: User, conversation_id: str | None, first_prompt: str
) -> Conversation:
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
_FOLLOWUP_RE = re.compile(
    r"^(and|also|but|so|then|ok(ay)?|what about|how about|what of|go deeper|"
    r"more detail|simpler|again)\b"
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
    lines = [f"{'Student' if r == 'user' else 'Tutor'}: {c[:400]}" for r, c in recent]
    return "Earlier in this conversation:\n" + "\n".join(lines)


# ------------------------------------------------------------------- planning
def _plan(db: Session, user: User, request: QueryRequest, rq: str) -> RetrievalPlan:
    if request.compare_document_ids:
        return RetrievalPlan(
            mode="pinpoint",
            k=max(request.top_k, settings.top_k_default),
            reason="comparing the materials you selected",
        )
    return plan_retrieval(
        db, user, rq, request.top_k,
        document_id=request.document_id, intent=request.intent, category_id=request.category_id,
    )


# ------------------------------------------------------------------- retrieval
def _retrieve(
    db: Session,
    user: User,
    request: QueryRequest,
    plan: RetrievalPlan,
    rq: str,
    *,
    conversation_id: str | None = None,
) -> list[RetrievedChunk]:
    with _tracer.start_as_current_span("rag.retrieve") as span:
        span.set_attribute("plan.mode", plan.mode)
        compare_ids = request.compare_document_ids or None
        doc_scope = compare_ids or ([plan.document_id] if plan.document_id else None)
        scope = Scope(
            user_id=user.id,
            category=request.category_id,
            document_ids=doc_scope,
            # Materials attached to this chat are always in scope, on top of any
            # category / document filter.
            conversation_id=conversation_id if not compare_ids else None,
        )

        if plan.mode == "document" and plan.document_id:
            results = fetch_document_chunks(db, plan.document_id, scope, plan.k)
        else:
            results = hybrid_search(
                db, query=rq, embedding=embed_text(rq),
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
    p_by_marker = {p.marker: p for p in passages}
    rc_by_id = {r.chunk.id: r for r in retrieved}
    valid = {u.marker for u in uses if u.marker in p_by_marker}
    if not valid:
        return _MARKER_RE.sub("", answer_text).strip(), []

    ordered: list[int] = []
    for m in (int(x) for x in _MARKER_RE.findall(answer_text)):
        if m in valid and m not in ordered:
            ordered.append(m)

    text = answer_text
    if not ordered:
        text, ordered = _splice_markers(text, uses, passages, valid)
    for use in uses:
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
                page=(rc.chunk.metadata_json or {}).get("page") if rc else None,
                quote=quote[:600],
                score=round(rc.score if rc else p.score, 4),
            )
        )
    return text, cites


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
    level: str,
) -> AnswerResponse:
    answer_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    compare = bool(request.compare_document_ids)
    source_chunks = _source_chunks(retrieved)

    answer_text = synth.answer.strip()
    answer_text, citations = _normalise_citations(answer_text, synth.citations, passages, retrieved)
    grounded = bool(citations) and synth.grounded
    confidence = _confidence(synth.confidence, retrieved, citations, plan.mode)
    label = _label(confidence)

    # "insufficient" = the tutor neither grounded the answer nor gave a confident
    # general-knowledge one.
    insufficient = not grounded and label == "insufficient"
    if insufficient:
        low = answer_text.lower()
        gave_up = (not answer_text) or low.startswith(
            ("i could not", "i couldn't", "i don't", "i do not", "i cannot", "i can't",
             "there is no", "no information")
        )
        if gave_up:
            answer_text = _insufficient_message(db, user, request.question)
            citations = []

    db.add(
        Answer(
            id=answer_id, user_id=user.id, conversation_id=conv.id,
            question=request.question, answer=answer_text, confidence=confidence,
            model=synth.model, category_id=request.category_id, compare_mode=compare,
            latency_ms=latency_ms,
            citations_json=[c.model_dump(by_alias=True) for c in citations],
            source_chunks_json=[s.model_dump(by_alias=True) for s in source_chunks],
            follow_ups_json=synth.follow_ups, usage_json=synth.usage or {},
        )
    )
    db.flush()

    response = AnswerResponse(
        id=answer_id, conversation_id=conv.id, message_id=message_id,
        question=request.question, answer=answer_text,
        confidence=confidence, confidence_label=label,  # type: ignore[arg-type]
        insufficient_evidence=insufficient, grounded=grounded,
        corrected=synth.corrected and not insufficient, compare_mode=compare,
        retrieval_mode=plan.mode, retrieval_note=plan.reason,
        explain_level=level,  # type: ignore[arg-type]
        citations=citations, source_chunks=source_chunks, follow_ups=synth.follow_ups,
        model=synth.model, provider=synth.provider, latency_ms=round(latency_ms, 2),
        usage=TokenUsage(**{k: synth.usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens")}),
        cached=False, created_at=datetime.now(UTC),
    )

    db.add(
        Message(
            id=message_id, conversation_id=conv.id, role=MessageRole.ASSISTANT,
            content=answer_text, answer_json=response.model_dump(by_alias=True, mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    conv.updated_at = datetime.now(UTC)
    db.commit()
    return response


def _refresh_context(
    conv: Conversation,
    question: str,
    answer_text: str,
    passages: list[llm.ContextPassage],
    mode: str,
) -> None:
    """Update the chat's running working memory in a background thread — it's a
    second model call and must never add to the user's wait."""
    if mode == "meta" or not settings.context_memory_enabled or not answer_text or not llm.provider_ready():
        return
    conv_id = conv.id
    prev = dict(conv.context_json or {})
    passage_lite = [
        llm.ContextPassage(p.marker, p.chunk_id, p.title, p.heading, p.text[:600], p.score)
        for p in passages[:4]
    ]

    def _run() -> None:
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            updated = llm.update_conversation_context(prev, question, answer_text, passage_lite)
            c = session.get(Conversation, conv_id)
            if c is not None:
                c.context_json = updated
                c.updated_at = datetime.now(UTC)
                session.commit()
        except Exception as exc:  # pragma: no cover - best effort
            session.rollback()
            logger.warning("context_update_failed", error=str(exc))
        finally:
            session.close()

    threading.Thread(target=_run, daemon=True).start()


# --------------------------------------------------------------------- meta
def _user_doc_count(db: Session, user: User) -> int:
    return int(
        db.execute(select(func.count(Document.id)).where(Document.user_id == user.id)).scalar_one()
    )


def _user_categories(db: Session, user: User) -> list[str]:
    rows = db.execute(
        select(Category.label).where(Category.user_id == user.id).order_by(Category.label)
    ).scalars().all()
    if rows:
        return list(rows)
    rows = db.execute(
        select(Document.category).where(Document.user_id == user.id).distinct()
    ).scalars().all()
    return sorted({(c or "General") for c in rows})


def _insufficient_message(db: Session, user: User, question: str) -> str:
    if _user_doc_count(db, user) == 0:
        return (
            "I can explain this from general knowledge, but you haven't uploaded any "
            "materials yet — add your notes, slides or a textbook chapter and I'll ground "
            "the explanation in them and cite the pages. Ask again and I'll do my best "
            "either way."
        )
    cats = _user_categories(db, user)
    cat_str = ", ".join(cats)
    return (
        f"I couldn't find this in your uploaded materials. You have: {cat_str}. "
        "Try rephrasing, name the note or deck it's in, or upload something that covers it "
        "— or ask me to explain it from general knowledge."
    )


def _meta_answer_response(
    request: QueryRequest, conv_id: str | None, msg_id: str | None, text: str
) -> AnswerResponse:
    return AnswerResponse(
        id=str(uuid.uuid4()), conversation_id=conv_id, message_id=msg_id,
        question=request.question, answer=text, confidence=1.0,
        confidence_label="high",  # type: ignore[arg-type]
        insufficient_evidence=False, grounded=False, compare_mode=False,
        retrieval_mode="meta", retrieval_note="",
        model="tutor", provider="tutor", latency_ms=0.0, cached=False,
        created_at=datetime.now(UTC),
    )


def _persist_meta(db: Session, conv: Conversation, request: QueryRequest, text: str) -> AnswerResponse:
    message_id = str(uuid.uuid4())
    response = _meta_answer_response(request, conv.id, message_id, text)
    db.add(
        Message(
            id=message_id, conversation_id=conv.id, role=MessageRole.ASSISTANT,
            content=text, answer_json=response.model_dump(by_alias=True, mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    conv.updated_at = datetime.now(UTC)
    db.commit()
    return response


def _cache_key(user: User, request: QueryRequest, level: str) -> str:
    return cache.cache_key(
        "answer", user.id, request.question.strip().lower(), request.top_k,
        request.category_id or "", request.document_id or "", request.intent,
        request.conversation_id or "", sorted(request.compare_document_ids or []),
        level, settings.active_model_name,
    )


# --------------------------------------------------------------------- public
def generate_answer(db: Session, user: User, request: QueryRequest) -> AnswerResponse:
    started = time.perf_counter()
    with _tracer.start_as_current_span("rag.generate_answer") as span:
        span.set_attribute("question.length", len(request.question))

        meta_kind = meta.detect(request.question)
        meta_text = meta.answer(db, user, meta_kind) if meta_kind else None
        if meta_text is not None:
            ephemeral = request.conversation_id is None and meta.is_ephemeral(meta_kind)
            if ephemeral:
                return _meta_answer_response(request, None, None, meta_text)
            conv = resolve_conversation(db, user, request.conversation_id, request.question)
            db.add(Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=MessageRole.USER,
                           content=request.question, created_at=datetime.now(UTC)))
            return _persist_meta(db, conv, request, meta_text)

        conv = resolve_conversation(db, user, request.conversation_id, request.question)
        history = _recent_turns(db, conv)
        db.add(Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=MessageRole.USER,
                       content=request.question, created_at=datetime.now(UTC)))

        level = _resolve_level(db, user, request)
        student = _student_level(db, user, request)
        # A chat with a running context evolves turn to turn — don't serve a
        # cached answer that predates the current understanding.
        cacheable = not (conv.context_json or {})
        key = _cache_key(user, request, level)
        if cacheable and not request.bypass_cache:
            hit = cache.get_json(key)
            if hit:
                hit["cached"] = True
                hit["conversationId"] = conv.id
                cached = AnswerResponse.model_validate(hit)
                msg = Message(id=str(uuid.uuid4()), conversation_id=conv.id,
                              role=MessageRole.ASSISTANT, content=cached.answer,
                              answer_json=hit, created_at=datetime.now(UTC))
                db.add(msg)
                conv.updated_at = datetime.now(UTC)
                db.commit()
                cached.message_id = msg.id
                return cached

        rq = _contextual_query(request.question, history)
        plan = _plan(db, user, request, rq)
        retrieved = _retrieve(db, user, request, plan, rq, conversation_id=conv.id)
        passages = _passages(retrieved)
        synth = llm.synthesize(
            request.question, passages,
            compare=bool(request.compare_document_ids), mode=plan.mode,
            level=level, student_level=student, history=_history_block(history),
            conversation_context=llm.render_context(conv.context_json or {}),
        )
        latency_ms = (time.perf_counter() - started) * 1000
        response = _assemble(db, user, conv, request, retrieved, synth, passages, latency_ms, plan, level)
        if cacheable and not response.insufficient_evidence:
            cache.set_json(key, response.model_dump(by_alias=True))
        _refresh_context(conv, request.question, response.answer, passages, plan.mode)
        span.set_attribute("confidence", response.confidence)
        return response


async def stream_answer(db: Session, user: User, request: QueryRequest) -> AsyncIterator[dict]:
    """Yield SSE frames: start → grounding → token* → final."""
    started = time.perf_counter()

    meta_kind = meta.detect(request.question)
    meta_text = meta.answer(db, user, meta_kind) if meta_kind else None
    if meta_text is not None:
        ephemeral = request.conversation_id is None and meta.is_ephemeral(meta_kind)
        if ephemeral:
            response = _meta_answer_response(request, None, None, meta_text)
            yield {"type": "start", "payload": {"question": request.question, "conversationId": ""}}
        else:
            conv = resolve_conversation(db, user, request.conversation_id, request.question)
            db.add(Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=MessageRole.USER,
                           content=request.question, created_at=datetime.now(UTC)))
            db.flush()
            yield {"type": "start", "payload": {"question": request.question, "conversationId": conv.id}}
            response = _persist_meta(db, conv, request, meta_text)
        for i, w in enumerate(meta_text.split(" ")):
            yield {"type": "token", "payload": {"text": (" " if i else "") + w}}
        yield {"type": "final", "payload": response.model_dump(by_alias=True, mode="json")}
        return

    conv = resolve_conversation(db, user, request.conversation_id, request.question)
    history = _recent_turns(db, conv)
    db.add(Message(id=str(uuid.uuid4()), conversation_id=conv.id, role=MessageRole.USER,
                   content=request.question, created_at=datetime.now(UTC)))
    db.flush()
    yield {"type": "start", "payload": {"question": request.question, "conversationId": conv.id}}

    level = _resolve_level(db, user, request)
    student = _student_level(db, user, request)
    cacheable = not (conv.context_json or {})
    rq = _contextual_query(request.question, history)
    plan = _plan(db, user, request, rq)
    retrieved = _retrieve(db, user, request, plan, rq, conversation_id=conv.id)
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
        request.question, passages,
        compare=bool(request.compare_document_ids), mode=plan.mode,
        level=level, student_level=student, history=_history_block(history),
        conversation_context=llm.render_context(conv.context_json or {}),
    )

    buf = ""
    words = synth.answer.split(" ")
    for i, w in enumerate(words):
        buf += (" " if i else "") + w
        if len(buf) >= 18 or i == len(words) - 1:
            yield {"type": "token", "payload": {"text": buf}}
            buf = ""

    latency_ms = (time.perf_counter() - started) * 1000
    response = _assemble(db, user, conv, request, retrieved, synth, passages, latency_ms, plan, level)
    if cacheable and not response.insufficient_evidence and not request.bypass_cache:
        cache.set_json(_cache_key(user, request, level), response.model_dump(by_alias=True))
    yield {"type": "final", "payload": response.model_dump(by_alias=True, mode="json")}
    # The answer is on the client now — refresh the chat's working memory without
    # making the user wait for a second model call.
    _refresh_context(conv, request.question, response.answer, passages, plan.mode)


def count_message_count(db: Session, conversation_id: str) -> int:
    return int(
        db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        ).scalar_one()
    )
