"""Conversation (chat thread) management — one per purpose, per user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Conversation, Message, User
from app.models.schemas import (
    AnswerResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _owned(db: Session, user: User, conversation_id: str) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ConversationRead]:
    last_at = func.max(Message.created_at)
    count = func.count(Message.id)
    rows = db.execute(
        select(Conversation, count, last_at)
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id, Conversation.archived.is_(False))
        .group_by(Conversation.id)
        .order_by(func.coalesce(last_at, Conversation.created_at).desc())
    ).all()
    return [
        ConversationRead(
            id=c.id,
            title=c.title,
            message_count=int(n or 0),
            last_message_at=lm,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c, n, lm in rows
    ]


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ConversationDetail:
    conv = Conversation(id=str(uuid.uuid4()), user_id=user.id, title=body.title.strip() or "New chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        message_count=0,
        last_message_at=None,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[],
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ConversationDetail:
    conv = _owned(db, user, conversation_id)
    messages = db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at, Message.role.desc())
    ).scalars().all()
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        message_count=len(messages),
        last_message_at=messages[-1].created_at if messages else None,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageRead(
                id=m.id,
                role=m.role.value,  # type: ignore[arg-type]
                content=m.content,
                answer=AnswerResponse.model_validate(m.answer_json) if m.answer_json else None,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationRead)
def rename_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationRead:
    conv = _owned(db, user, conversation_id)
    conv.title = body.title.strip()
    db.commit()
    return ConversationRead(
        id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at
    )


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    conv = _owned(db, user, conversation_id)
    db.delete(conv)
    db.commit()
    return {"deleted": conversation_id}
