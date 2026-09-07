"""Lightweight cross-encoder-style reranker.

No model download required: blends the dense score, the sparse score, exact
term coverage, heading relevance and a mild length prior into a single
``rerank_score`` in ``[0, 1]``. This measurably sharpens ordering on top of RRF
and gives the confidence estimator a calibrated signal. Swap in a hosted
cross-encoder (Cohere Rerank, bge-reranker, ...) behind the same interface for
production.
"""

from __future__ import annotations

import math
import re

from app.core.config import get_settings
from app.core.telemetry import tracer
from app.services.vectorstore import RetrievedChunk

settings = get_settings()
_tracer = tracer(__name__)

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was",
    "were", "be", "by", "with", "as", "at", "it", "this", "that", "what", "which",
    "who", "when", "where", "how", "why", "do", "does", "did", "our", "we", "i",
    "can", "could", "should", "would", "will", "may", "about", "from", "any",
}


def _terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower()) if t not in _STOP and len(t) > 2]


def rerank(query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if not candidates or not settings.rerank_enabled:
        return candidates

    with _tracer.start_as_current_span("reranker.rerank") as span:
        span.set_attribute("candidates", len(candidates))
        q_terms = _terms(query)
        q_set = set(q_terms)

        # Deterministic (offline) embeddings aren't semantic, so the dense score
        # is noise — shift its weight onto the lexical signals.
        semantic = settings.embedding_provider != "deterministic"
        w_vec = 0.34 if semantic else 0.0
        w_kw = 0.20 if semantic else 0.30
        w_cov = 0.24 if semantic else 0.36
        w_den = 0.08 if semantic else 0.14

        for rc in candidates:
            body = rc.chunk.text.lower()
            body_terms = _terms(rc.chunk.text)
            body_set = set(body_terms)

            coverage = len(q_set & body_set) / len(q_set) if q_set else 0.0
            phrase = 1.0 if q_terms and " ".join(q_terms[:4]) in body else 0.0
            heading_hit = 0.0
            if rc.chunk.heading:
                h_set = set(_terms(rc.chunk.heading))
                heading_hit = len(q_set & h_set) / len(q_set) if q_set else 0.0
            density = (len(q_set & body_set)) / math.sqrt(max(len(body_terms), 1))
            length_prior = 1.0 - min(abs(rc.chunk.token_count - 260) / 600, 0.5)

            score = (
                w_vec * rc.vector_score
                + w_kw * rc.keyword_score
                + w_cov * coverage
                + w_den * min(density, 1.0)
                + 0.06 * heading_hit
                + 0.04 * phrase
                + 0.04 * length_prior
            )
            rc.rerank_score = max(0.0, min(1.0, score))
            rc.debug.update(coverage=round(coverage, 3), density=round(density, 3), phrase=phrase)

        ordered = sorted(candidates, key=lambda r: r.rerank_score or 0.0, reverse=True)

        # Gentle calibration: keep the top score anchored to its own strength
        # (so a weak best match still reads as weak) but spread the tail down so
        # the retrieval-confidence signal has range. No-op when nothing separates.
        raw = [r.rerank_score or 0.0 for r in ordered]
        if raw and max(raw) - min(raw) > 0.06:
            hi, lo = max(raw), min(raw)
            for r in ordered:
                spread = ((r.rerank_score or 0.0) - lo) / (hi - lo)
                r.rerank_score = round(hi * (0.35 + 0.65 * spread), 4)
        return ordered
