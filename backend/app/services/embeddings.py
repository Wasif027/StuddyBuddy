"""Embedding provider abstraction.

Providers
---------
``openai``        — real embeddings via the OpenAI API (needs ``OPENAI_API_KEY``).
``deterministic`` — offline, hash-seeded pseudo-embeddings. Not semantic, but
                    stable and unit-testable so the whole pipeline runs with zero
                    external dependencies in CI / local dev.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import tracer

logger = get_logger(__name__)
settings = get_settings()
_tracer = tracer(__name__)

# Small feature vocabulary keeps deterministic embeddings partly lexical, so
# passages that share salient words land closer together than pure hashing.
_VOCAB_SIZE = 4096


def _hash_bucket(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big") % _VOCAB_SIZE


def _deterministic(text: str, dim: int) -> list[float]:
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big"))
    base = rng.standard_normal(dim)

    tokens = [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 2]
    if tokens:
        lexical = np.zeros(dim)
        for tok in tokens:
            bucket = _hash_bucket(tok)
            tok_rng = np.random.default_rng(bucket)
            lexical += tok_rng.standard_normal(dim)
        lexical /= max(len(tokens), 1)
        vec = 0.35 * base + 0.65 * lexical
    else:
        vec = base

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.astype(float).tolist()


@lru_cache(maxsize=2048)
def _cached_deterministic(text: str, dim: int) -> tuple[float, ...]:
    return tuple(_deterministic(text, dim))


def _openai(texts: list[str]) -> list[list[float]]:  # pragma: no cover - network
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.resolved_embedding_api_key or "not-needed",
        base_url=settings.resolved_embedding_base_url or None,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
    dim = settings.embedding_dim
    try:
        resp = client.embeddings.create(model=settings.embedding_model, input=texts, dimensions=dim)
    except TypeError:
        resp = client.embeddings.create(model=settings.embedding_model, input=texts)
    vectors = [list(d.embedding) for d in resp.data]

    if vectors and len(vectors[0]) < dim:
        raise ValueError(f"embedding model returned {len(vectors[0])} dims, need >= EMBEDDING_DIM ({dim})")
    # Truncate Matryoshka embeddings to `dim` if needed, then L2-normalise so
    # stored vectors are unit length (cosine == dot product downstream).
    return [_renorm(v[:dim]) for v in vectors]


def _renorm(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=float)
    n = np.linalg.norm(arr)
    return (arr / n).tolist() if n else vec


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Length of each vector == ``settings.embedding_dim``."""
    if not texts:
        return []
    with _tracer.start_as_current_span("embeddings.embed_texts") as span:
        span.set_attribute("count", len(texts))
        span.set_attribute("provider", settings.embedding_provider)
        if settings.embedding_provider == "openai" and settings.embedding_configured:
            try:
                return _openai(texts)
            except Exception as exc:
                logger.warning("openai_embeddings_failed_falling_back", error=str(exc))
        dim = settings.embedding_dim
        return [list(_cached_deterministic(t, dim)) for t in texts]


def embed_text(text: str) -> list[float]:
    """Embed a single string. Query-side callers hit this on every request, so
    real (network) embeddings get a short-TTL cache keyed on the normalised text —
    re-asks and rapid iteration skip the round trip. Deterministic embeddings are
    already memoised in-process, so they bypass the cache entirely."""
    if settings.embedding_provider != "openai" or not settings.embedding_configured:
        return embed_texts([text])[0]

    from app.core import cache

    key = cache.cache_key("embed", settings.embedding_model, " ".join(text.split()).lower())
    hit = cache.get_json(key)
    if isinstance(hit, list) and hit:
        return hit
    try:
        vec = _openai([text])[0]
    except Exception as exc:  # network hiccup → don't cache the deterministic fallback
        logger.warning("openai_embeddings_failed_falling_back", error=str(exc))
        return list(_cached_deterministic(text, settings.embedding_dim))
    cache.set_json(key, vec, ttl=300)
    return vec
