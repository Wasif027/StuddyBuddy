"""Serialisation helper for AI next-step suggestions (kept import-light)."""

from __future__ import annotations

from app.models.orm import Suggestion
from app.models.schemas import SuggestionRead


def to_read(
    s: Suggestion,
    *,
    conversation_title: str | None = None,
    conversation_deleted: bool = False,
) -> SuggestionRead:
    return SuggestionRead(
        id=s.id,
        text=s.text,
        rationale=s.rationale,
        priority=s.priority,  # type: ignore[arg-type]
        kind=s.kind,  # type: ignore[arg-type]
        decision=s.decision.value,  # type: ignore[arg-type]
        note=s.note,
        reject_depth=s.reject_depth,
        created_at=s.created_at,
        decided_at=s.decided_at,
        question=s.question or None,
        conversation_id=s.conversation_id,
        message_id=s.message_id,
        conversation_title=conversation_title,
        conversation_deleted=conversation_deleted,
    )
