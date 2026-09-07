"""AI next-step suggestions — a decision log, not an execution engine.

Each suggestion is accepted / rejected / marked already-done by the user. A reject
asks the model for one alternative (capped). The history view lists every
suggestion ever and deep-links back to the chat + message it came from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Answer, Conversation, Suggestion, SuggestionDecision, User
from app.models.schemas import (
    SuggestionDecisionRequest,
    SuggestionDecisionResponse,
    SuggestionRead,
)
from app.services import llm
from app.services.llm import ContextPassage
from app.services.suggestions import to_read

settings = get_settings()
router = APIRouter(prefix="/suggestions", tags=["suggestions"])

_DECISION_MAP = {
    "accept": SuggestionDecision.ACCEPTED,
    "reject": SuggestionDecision.REJECTED,
    "done": SuggestionDecision.DONE,
}


def _owned(db: Session, user: User, suggestion_id: str) -> Suggestion:
    s = db.get(Suggestion, suggestion_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="suggestion not found")
    return s


@router.get("", response_model=list[SuggestionRead])
def list_suggestions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status: Literal["pending", "accepted", "rejected", "done"] | None = None,
    conversation_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[SuggestionRead]:
    stmt = (
        select(Suggestion, Conversation.title)
        .outerjoin(Conversation, Conversation.id == Suggestion.conversation_id)
        .where(Suggestion.user_id == user.id, Suggestion.superseded_by_id.is_(None))
        .order_by(Suggestion.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(Suggestion.decision == SuggestionDecision(status))
    if conversation_id:
        stmt = stmt.where(Suggestion.conversation_id == conversation_id)
    rows = db.execute(stmt).all()
    return [
        to_read(
            s,
            conversation_title=title,
            conversation_deleted=s.conversation_id is None,
        )
        for s, title in rows
    ]


def _rejected_chain_texts(db: Session, s: Suggestion) -> list[str]:
    """Every rejected step in this slot's chain, oldest first."""
    texts: list[str] = []
    cur: Suggestion | None = s
    # walk back to the root
    while cur and cur.replaces_id:
        cur = db.get(Suggestion, cur.replaces_id)
    while cur:
        texts.append(cur.text)
        nxt = (
            db.execute(select(Suggestion).where(Suggestion.replaces_id == cur.id)).scalars().first()
        )
        cur = nxt
    return texts


def _answer_context(db: Session, s: Suggestion) -> tuple[str, list[ContextPassage]]:
    answer = db.get(Answer, s.answer_id) if s.answer_id else None
    if not answer:
        return "", []
    passages = [
        ContextPassage(
            marker=i + 1,
            chunk_id=str(c.get("chunkId", "")),
            title=str(c.get("title", "")),
            heading=c.get("heading"),
            text=str(c.get("text", "")),
            score=float(c.get("score", 0.0) or 0.0),
        )
        for i, c in enumerate((answer.source_chunks_json or [])[:5])
    ]
    return answer.answer, passages


@router.post("/{suggestion_id}/decide", response_model=SuggestionDecisionResponse)
def decide_suggestion(
    suggestion_id: str,
    body: SuggestionDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SuggestionDecisionResponse:
    s = _owned(db, user, suggestion_id)
    s.decision = _DECISION_MAP[body.decision]
    if body.note is not None:
        s.note = body.note.strip() or None
    s.decided_at = datetime.now(UTC)
    db.flush()

    alternative: SuggestionRead | None = None
    if (
        body.decision == "reject"
        and settings.suggestions_enabled
        and s.reject_depth < settings.suggestion_max_alternatives
        and llm.provider_ready()
    ):
        answer_text, passages = _answer_context(db, s)
        rejected = _rejected_chain_texts(db, s)
        step = llm.suggest_alternative(s.question, answer_text, passages, rejected)
        if step:
            alt = Suggestion(
                user_id=user.id,
                answer_id=s.answer_id,
                conversation_id=s.conversation_id,
                message_id=s.message_id,
                question=s.question,
                text=step.text,
                rationale=step.rationale or None,
                priority=step.priority,
                kind=step.kind,
                decision=SuggestionDecision.PENDING,
                reject_depth=s.reject_depth + 1,
                replaces_id=s.id,
            )
            db.add(alt)
            db.flush()
            s.superseded_by_id = alt.id
            alternative = to_read(alt)

    db.commit()
    return SuggestionDecisionResponse(
        suggestion=to_read(s),
        alternative=alternative,
        message=f"Suggestion {body.decision}ed" if body.decision != "done" else "Marked as done",
    )
