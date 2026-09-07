"""Category navigator data for the left sidebar."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Chunk, Document, DocumentStatus, User
from app.models.schemas import DocumentCategory

router = APIRouter(prefix="/categories", tags=["categories"])

_LABELS = {
    "policy": "Policies",
    "contract": "Contracts",
    "runbook": "Runbooks",
    "tech-doc": "Technical Docs",
    "meeting-notes": "Meeting Notes",
    "incident": "Incident Reports",
    "hr": "HR",
    "finance": "Finance",
    "legal": "Legal",
    "security": "Security",
    "sales": "Sales",
    "data": "Data & Reports",
    "deck": "Decks",
    "uncategorized": "Uncategorized",
}


def _label(cat: str) -> str:
    return _LABELS.get(cat, cat.replace("-", " ").replace("_", " ").title())


@router.get("", response_model=list[DocumentCategory])
def list_categories(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DocumentCategory]:
    rows = db.execute(
        select(
            Document.category,
            func.count(func.distinct(Document.id)),
            func.count(Chunk.id),
            func.sum(case((Document.status == DocumentStatus.PROCESSING, 1), else_=0)),
            func.sum(case((Document.status == DocumentStatus.FAILED, 1), else_=0)),
        )
        .select_from(Document)
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(Document.user_id == user.id)
        .group_by(Document.category)
        .order_by(Document.category)
    ).all()

    out: list[DocumentCategory] = []
    for category, doc_count, chunk_count, processing, failed in rows:
        cat = category or "uncategorized"
        if not doc_count:
            status = "empty"
        elif failed:
            status = "failed"
        elif processing:
            status = "processing"
        elif not chunk_count:
            status = "indexing"
        else:
            status = "ready"
        out.append(
            DocumentCategory(
                id=cat,
                label=_label(cat),
                doc_count=int(doc_count or 0),
                chunk_count=int(chunk_count or 0),
                status=status,  # type: ignore[arg-type]
            )
        )
    return out
