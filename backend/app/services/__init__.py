"""Services package — business logic (embeddings, retrieval, rerank, RAG, analytics)."""

from app.services.embeddings import embed_text, embed_texts
from app.services.ingestion import ingest_content, parse_upload
from app.services.rag import generate_answer, stream_answer
from app.services.reranker import rerank
from app.services.vectorstore import hybrid_search

__all__ = [
    "embed_text",
    "embed_texts",
    "ingest_content",
    "parse_upload",
    "generate_answer",
    "stream_answer",
    "rerank",
    "hybrid_search",
]
