"""Study-material ingestion & management API (per-user)."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.telemetry import tracer
from app.models.orm import Chunk, Conversation, Document, DocumentSlide, Note, NoteKind, User
from app.models.schemas import (
    DocumentChunkPreview,
    DocumentDetail,
    DocumentRead,
    IngestionRequest,
    IngestionResponse,
    SlidePreview,
)
from app.services.catalog import ensure_category
from app.services.ingestion import (
    IMAGE_UPLOAD_TYPES,
    SUPPORTED_UPLOAD_TYPES,
    ParseError,
    UnsupportedFileType,
    ingest_content,
    parse_upload,
)

_tracer = tracer(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()


def _resolve_conv(db: Session, user: User, conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    conv = db.get(Conversation, conversation_id)
    return conv.id if conv and conv.user_id == user.id else None


def _slide_count(db: Session, document_id: str) -> int:
    return int(
        db.execute(
            select(func.count(DocumentSlide.id)).where(DocumentSlide.document_id == document_id)
        ).scalar_one()
    )


def _to_read(doc: Document, chunk_count: int, slide_count: int = 0) -> DocumentRead:
    return DocumentRead(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        source_type=doc.source_type,
        status=doc.status.value,
        error=doc.error,
        chunk_count=chunk_count,
        slide_count=slide_count,
        char_count=doc.char_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _ingestion_response(
    doc: Document, chunks: int, deduped: bool, started: float,
    *, note_id: str | None = None, detected_kind: str | None = None,
) -> IngestionResponse:
    return IngestionResponse(
        document_id=doc.id,
        document_title=doc.title,
        status=doc.status.value,
        chunks_created=chunks,
        char_count=doc.char_count,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        deduplicated=deduped,
        note_id=note_id,
        detected_kind=detected_kind,
    )


@router.post("", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
def ingest_document(
    request: IngestionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> IngestionResponse:
    started = time.perf_counter()
    category = ensure_category(db, user, request.category) if request.category else None
    doc, chunks, deduped = ingest_content(
        db,
        user_id=user.id,
        title=request.title,
        content=request.content,
        category=category,
        source_type=request.source_type,
        metadata=request.metadata,
        conversation_id=_resolve_conv(db, user, request.conversation_id),
    )
    return _ingestion_response(doc, chunks, deduped, started)


@router.post("/upload", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    title: str | None = Form(default=None),
    hint: str | None = Form(default=None),
    conversation_id: str | None = Form(default=None),
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
    name = file.filename or "upload"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    slug = ensure_category(db, user, category) if category else None
    conv_id = _resolve_conv(db, user, conversation_id)

    # ---------- image scan → vision ----------
    if ext in IMAGE_UPLOAD_TYPES:
        from app.services.vision import describe_image

        try:
            result = describe_image(raw, name, hint=hint)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if not slug and result.subject:
            slug = ensure_category(db, user, result.subject)

        doc, chunks, deduped = ingest_content(
            db,
            user_id=user.id,
            title=title or result.title,
            content=result.embed_text,
            category=slug,
            source_type="image",
            metadata={
                "filename": name,
                "content_type": file.content_type,
                "kind": "image",
                "imageKind": result.kind,
            },
            conversation_id=conv_id,
        )

        note_id: str | None = None
        if result.kind == "timetable" and result.routine.get("days"):
            note = Note(
                id=str(uuid.uuid4()), user_id=user.id, category=slug, kind=NoteKind.ROUTINE,
                title=title or result.title or "My timetable", body_md=result.markdown,
                structured_json=result.routine, source="image", source_ref=doc.id,
            )
            db.add(note)
            db.commit()
            note_id = note.id
        return _ingestion_response(
            doc, chunks, deduped, started, note_id=note_id, detected_kind=result.kind
        )

    # ---------- document ----------
    try:
        parsed = parse_upload(name, raw)
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
        category=slug,
        source_type=parsed.kind,
        metadata={"filename": name, "content_type": file.content_type},
        slides=parsed.slides,
        conversation_id=conv_id,
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
    chunk_counts = (
        select(Chunk.document_id, func.count(Chunk.id).label("n")).group_by(Chunk.document_id).subquery()
    )
    slide_counts = (
        select(DocumentSlide.document_id, func.count(DocumentSlide.id).label("n"))
        .group_by(DocumentSlide.document_id).subquery()
    )
    stmt = (
        select(Document, func.coalesce(chunk_counts.c.n, 0), func.coalesce(slide_counts.c.n, 0))
        .outerjoin(chunk_counts, chunk_counts.c.document_id == Document.id)
        .outerjoin(slide_counts, slide_counts.c.document_id == Document.id)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    if category:
        stmt = stmt.where(Document.category == category)
    return [_to_read(doc, int(n), int(sn)) for doc, n, sn in db.execute(stmt).all()]


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
    slides = db.execute(
        select(DocumentSlide).where(DocumentSlide.document_id == document_id).order_by(DocumentSlide.index)
    ).scalars().all()
    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        source_type=doc.source_type,
        status=doc.status.value,
        chunk_count=len(chunks),
        slide_count=len(slides),
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
        slides=[
            SlidePreview(
                index=s.index, title=s.title, bullets=list(s.bullets_json or []),
                notes=s.notes, has_chart=s.has_chart, has_table=s.has_table, importance=s.data_score,
            )
            for s in slides
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
    cache.invalidate_prefix("studybuddy:")
    return {"deleted": document_id}
