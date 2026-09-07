"""Hybrid retrieval over the ``chunks`` table.

Combines dense vector search (pgvector cosine, HNSW index) with sparse keyword
search (PostgreSQL full-text ``ts_rank_cd``) and fuses the two ranked lists with
Reciprocal Rank Fusion. Falls back to a trigram similarity search when a query
produces no lexical matches. Every search is scoped to a single owner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import Float, Select, func, select
from sqlalchemy.orm import Session, contains_eager

from app.core.config import get_settings
from app.core.telemetry import tracer
from app.models.orm import Chunk, Document

settings = get_settings()
_tracer = tracer(__name__)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    vector_score: float = 0.0
    keyword_score: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None
    debug: dict = field(default_factory=dict)

    @property
    def score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.fused_score


@dataclass
class Scope:
    user_id: str
    category: str | None = None
    document_ids: Sequence[str] | None = None


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _apply_scope(stmt: Select, scope: Scope) -> Select:
    # contains_eager: the Document is already joined for scoping, so load it onto
    # the Chunk in the same round trip — callers read chunk.document.title/category.
    stmt = (
        stmt.join(Document, Document.id == Chunk.document_id)
        .options(contains_eager(Chunk.document))
        .where(Document.user_id == scope.user_id)
    )
    if scope.category:
        stmt = stmt.where(Document.category == scope.category)
    if scope.document_ids:
        stmt = stmt.where(Document.id.in_(list(scope.document_ids)))
    return stmt


def vector_search(db: Session, embedding: list[float], k: int, scope: Scope) -> list[tuple[Chunk, float]]:
    distance = Chunk.embedding.cosine_distance(embedding).label("distance")
    stmt = _apply_scope(select(Chunk, distance).where(Chunk.embedding.is_not(None)), scope)
    rows = db.execute(stmt.order_by(distance).limit(k)).all()
    return [(row[0], _clamp(1.0 - float(row[1]))) for row in rows]


def keyword_search(db: Session, query: str, k: int, scope: Scope) -> list[tuple[Chunk, float]]:
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.text_tsv, tsquery).label("rank")
    stmt = _apply_scope(select(Chunk, rank).where(Chunk.text_tsv.op("@@")(tsquery)), scope)
    rows = db.execute(stmt.order_by(rank.desc()).limit(k)).all()
    if not rows:
        rows = _trigram_search(db, query, k, scope)
    return [(c, _clamp(float(r) / (float(r) + 0.5))) for c, r in rows]


def _trigram_search(db: Session, query: str, k: int, scope: Scope):
    sim = func.similarity(Chunk.text, query).cast(Float).label("rank")
    stmt = _apply_scope(select(Chunk, sim).where(sim > 0.05), scope)
    return db.execute(stmt.order_by(sim.desc()).limit(k)).all()


def fetch_document_chunks(db: Session, document_id: str, scope: Scope, limit: int) -> list[RetrievedChunk]:
    """Every chunk of one document, in reading order — for whole-document reads.

    No ranking: the document *is* the evidence. ``fused_score`` is set to a
    neutral-high value so downstream threshold / confidence logic doesn't treat
    a faithfully-loaded document as weak.
    """
    stmt = _apply_scope(select(Chunk), scope).where(Chunk.document_id == document_id)
    rows = db.execute(stmt.order_by(Chunk.chunk_index).limit(limit)).scalars().all()
    return [RetrievedChunk(chunk=c, fused_score=1.0) for c in rows]


def diversify(results: list[RetrievedChunk], per_document_cap: int) -> list[RetrievedChunk]:
    """Keep at most ``per_document_cap`` chunks per document, preserving order.

    Used for 'overview' questions so one dense document can't crowd out the rest
    of the knowledge base.
    """
    seen: dict[str, int] = {}
    kept: list[RetrievedChunk] = []
    for rc in results:
        doc_id = rc.chunk.document_id
        if seen.get(doc_id, 0) >= per_document_cap:
            continue
        seen[doc_id] = seen.get(doc_id, 0) + 1
        kept.append(rc)
    return kept


def hybrid_search(
    db: Session,
    *,
    query: str,
    embedding: list[float],
    k: int,
    scope: Scope,
    candidates: int | None = None,
) -> list[RetrievedChunk]:
    """Return up to ``k`` chunks ranked by Reciprocal Rank Fusion."""
    cand = candidates or settings.retrieval_candidates
    rrf_k = settings.rrf_k

    with _tracer.start_as_current_span("vectorstore.hybrid_search") as span:
        span.set_attribute("k", k)
        span.set_attribute("candidates", cand)
        span.set_attribute("scope.category", scope.category or "all")
        span.set_attribute("scope.documents", len(scope.document_ids or []))

        vec = vector_search(db, embedding, cand, scope)
        kw = keyword_search(db, query, cand, scope)

        merged: dict[str, RetrievedChunk] = {}
        for rank, (chunk, s) in enumerate(vec):
            merged[chunk.id] = RetrievedChunk(chunk=chunk, vector_score=s, vector_rank=rank)
        for rank, (chunk, s) in enumerate(kw):
            rc = merged.get(chunk.id) or RetrievedChunk(chunk=chunk)
            rc.keyword_score = s
            rc.keyword_rank = rank
            merged[chunk.id] = rc

        for rc in merged.values():
            fused = 0.0
            if rc.vector_rank is not None:
                fused += 1.0 / (rrf_k + rc.vector_rank + 1)
            if rc.keyword_rank is not None:
                fused += 1.0 / (rrf_k + rc.keyword_rank + 1)
            rc.fused_score = fused

        ordered = sorted(merged.values(), key=lambda r: r.fused_score, reverse=True)
        if ordered:
            hi = ordered[0].fused_score or 1.0
            for rc in ordered:
                rc.fused_score = _clamp(rc.fused_score / hi) if hi else 0.0

        span.set_attribute("vector_hits", len(vec))
        span.set_attribute("keyword_hits", len(kw))
        span.set_attribute("fused_hits", len(ordered))
        return ordered[:k]
