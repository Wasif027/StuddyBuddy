"""Notes, learning log, and saved explanations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Message, Note, NoteKind, PracticeSet, User
from app.models.schemas import (
    NoteCreate,
    NoteKindValue,
    NoteRead,
    NoteUpdate,
    PracticeSetRead,
    SaveFromChatRequest,
)
from app.services.assessment import generate_practice_set
from app.services.catalog import ensure_category

router = APIRouter(prefix="/notes", tags=["notes"])


def _read(n: Note) -> NoteRead:
    return NoteRead(
        id=n.id, category=n.category, kind=n.kind.value, title=n.title, body_md=n.body_md,
        structured=n.structured_json or {}, source=n.source, source_ref=n.source_ref,
        pinned=n.pinned, created_at=n.created_at, updated_at=n.updated_at,
    )


def _owned(db: Session, user: User, note_id: str) -> Note:
    n = db.get(Note, note_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="note not found")
    return n


@router.get("", response_model=list[NoteRead])
def list_notes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    kind: NoteKindValue | None = None,
    category: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = 200,
) -> list[NoteRead]:
    stmt = select(Note).where(Note.user_id == user.id)
    if kind:
        stmt = stmt.where(Note.kind == NoteKind(kind))
    if category:
        stmt = stmt.where(Note.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Note.title.ilike(like), Note.body_md.ilike(like)))
    stmt = stmt.order_by(Note.pinned.desc(), Note.updated_at.desc()).limit(min(limit, 500))
    return [_read(n) for n in db.execute(stmt).scalars().all()]


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    body: NoteCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> NoteRead:
    category = ensure_category(db, user, body.category) if body.category else None
    n = Note(
        id=str(uuid.uuid4()), user_id=user.id, category=category,
        kind=NoteKind(body.kind), title=body.title.strip(), body_md=body.body_md,
        structured_json=body.structured or {}, source="manual", source_ref=body.source_ref,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return _read(n)


@router.get("/{note_id}", response_model=NoteRead)
def get_note(
    note_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> NoteRead:
    return _read(_owned(db, user, note_id))


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: str, body: NoteUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> NoteRead:
    n = _owned(db, user, note_id)
    if body.title is not None:
        n.title = body.title.strip()
    if body.body_md is not None:
        n.body_md = body.body_md
    if body.category is not None:
        n.category = ensure_category(db, user, body.category) if body.category else None
    if body.pinned is not None:
        n.pinned = body.pinned
    db.commit()
    db.refresh(n)
    return _read(n)


@router.delete("/{note_id}")
def delete_note(
    note_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    db.delete(_owned(db, user, note_id))
    db.commit()
    return {"deleted": note_id}


@router.post("/from-chat", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def save_from_chat(
    body: SaveFromChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> NoteRead:
    msg = db.get(Message, body.message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    conv = msg.conversation
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="message not found")
    title = (body.title or conv.title or "Saved explanation").strip()[:300]
    category = ensure_category(db, user, body.category) if body.category else None
    n = Note(
        id=str(uuid.uuid4()), user_id=user.id, category=category, kind=NoteKind.SAVED,
        title=title, body_md=msg.content, source="chat", source_ref=msg.id,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return _read(n)


@router.post("/{note_id}/quiz", response_model=PracticeSetRead, status_code=status.HTTP_201_CREATED)
def quiz_from_note(
    note_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PracticeSetRead:
    from app.routers.practice import _set_read

    n = _owned(db, user, note_id)
    topic = f"{n.title}\n\n{n.body_md}".strip()[:4000]
    ps = generate_practice_set(db, user, topic=topic, category=n.category)
    ps = db.get(PracticeSet, ps.id)
    return _set_read(db, user.id, ps)
