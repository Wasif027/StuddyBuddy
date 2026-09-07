"""Document ingestion & management API (per-user)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.telemetry import tracer
from app.models.orm import Chunk, Document, User
from app.models.schemas import (
    DocumentChunkPreview,
    DocumentDetail,
    DocumentRead,
    IngestionRequest,
    IngestionResponse,
)
from app.services.ingestion import (
    SUPPORTED_UPLOAD_TYPES,
    ParseError,
    UnsupportedFileType,
    ingest_content,
    parse_upload,
)

_tracer = tracer(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()


def _to_read(doc: Document, chunk_count: int) -> DocumentRead:
    return DocumentRead(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        source_type=doc.source_type,
        status=doc.status.value,
        error=doc.error,
        chunk_count=chunk_count,
        char_count=doc.char_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _ingestion_response(doc: Document, chunks: int, deduped: bool, started: float) -> IngestionResponse:
    return IngestionResponse(
        document_id=doc.id,
        document_title=doc.title,
        status=doc.status.value,
        chunks_created=chunks,
        char_count=doc.char_count,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        deduplicated=deduped,
    )


@router.post("", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
def ingest_document(
    request: IngestionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> IngestionResponse:
    started = time.perf_counter()
    doc, chunks, deduped = ingest_content(
        db,
        user_id=user.id,
        title=request.title,
        content=request.content,
        category=request.category,
        source_type=request.source_type,
        metadata=request.metadata,
    )
    return _ingestion_response(doc, chunks, deduped, started)


@router.post("/upload", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IngestionResponse:
    started = time.perf_counter()
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {settings.max_upload_bytes // (1024 * 1024)}MB limit",
        )
    try:
        parsed = parse_upload(file.filename or "document", raw)
    except UnsupportedFileType as exc:
        raise HTTPException(
            status_code=415, detail=f"{exc} — supported: {sorted(SUPPORTED_UPLOAD_TYPES)}"
        ) from exc
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not parsed.text.strip():
        raise HTTPException(status_code=422, detail="no readable content in this file")

    doc, chunks, deduped = ingest_content(
        db,
        user_id=user.id,
        title=title or parsed.title,
        content=parsed.text,
        category=category,
        source_type=parsed.kind,
        metadata={"filename": file.filename, "content_type": file.content_type},
        tables=parsed.tables,
        slides=parsed.slides,
    )
    return _ingestion_response(doc, chunks, deduped, started)


@router.get("", response_model=list[DocumentRead])
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    category: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[DocumentRead]:
    counts = (
        select(Chunk.document_id, func.count(Chunk.id).label("n")).group_by(Chunk.document_id).subquery()
    )
    stmt = (
        select(Document, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.document_id == Document.id)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    if category:
        stmt = stmt.where(Document.category == category)
    return [_to_read(doc, int(n)) for doc, n in db.execute(stmt).all()]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentDetail:
    doc = db.get(Document, document_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="document not found")
    chunks = db.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
    ).scalars().all()
    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        source_type=doc.source_type,
        status=doc.status.value,
        chunk_count=len(chunks),
        char_count=doc.char_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        metadata=doc.metadata_json or {},
        error=doc.error,
        chunks=[
            DocumentChunkPreview(
                chunk_index=c.chunk_index, heading=c.heading, text=c.text, token_count=c.token_count
            )
            for c in chunks
        ],
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    doc = db.get(Document, document_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="document not found")
    db.delete(doc)
    db.commit()
    cache.invalidate_prefix("ekdp:")
    return {"deleted": document_id}
