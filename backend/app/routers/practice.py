"""Practice questions — generate a tiered set, then grade answers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Attempt, PracticeSet, Question, User
from app.models.schemas import (
    AttemptRead,
    GradeRequest,
    GradeResponse,
    PracticeRequest,
    PracticeSetRead,
    PracticeSetSummary,
    QuestionRead,
)
from app.services.assessment import generate_practice_set, grade_attempt
from app.services.catalog import ensure_category

router = APIRouter(prefix="/practice", tags=["practice"])
settings = get_settings()

_ANSWER_UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".pdf"}


def _attempts_by_qid(db: Session, user_id: str, set_id: str) -> dict[str, Attempt]:
    rows = db.execute(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.practice_set_id == set_id)
        .order_by(Attempt.created_at)
    ).scalars().all()
    return {a.question_id: a for a in rows if a.question_id}


def _attempt_read(a: Attempt) -> AttemptRead:
    return AttemptRead(
        id=a.id, question_id=a.question_id, user_answer=a.user_answer, correct=a.correct,
        score=a.score, feedback=a.feedback, tier=a.tier,
        transcription=getattr(a, "transcription", None), created_at=a.created_at,
    )


def _question_read(q: Question, attempt: Attempt | None) -> QuestionRead:
    done = attempt is not None
    return QuestionRead(
        id=q.id, index=q.index, tier=q.tier.value, qtype=q.qtype.value, prompt=q.prompt,
        options=list(q.options_json or []), skill=q.skill,
        answer_mode=getattr(q, "answer_mode", "text") or "text",
        answer=q.answer if done else None,
        rubric=q.rubric if done else None,
        attempt=_attempt_read(attempt) if attempt else None,
    )


def _set_read(db: Session, user_id: str, ps: PracticeSet) -> PracticeSetRead:
    attempts = _attempts_by_qid(db, user_id, ps.id)
    qs = [_question_read(q, attempts.get(q.id)) for q in ps.questions]
    return PracticeSetRead(
        id=ps.id, topic=ps.topic, category=ps.category, study_level=ps.study_level,
        source=ps.source, document_id=ps.document_id, conversation_id=ps.conversation_id,
        model=ps.model, created_at=ps.created_at, questions=qs,
        answered=len(attempts),
        correct=sum(1 for a in attempts.values() if a.correct),
    )


def _owned_set(db: Session, user: User, set_id: str) -> PracticeSet:
    ps = db.execute(
        select(PracticeSet)
        .where(PracticeSet.id == set_id, PracticeSet.user_id == user.id)
        .options(selectinload(PracticeSet.questions))
    ).scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="practice set not found")
    return ps


@router.post("", response_model=PracticeSetRead, status_code=status.HTTP_201_CREATED)
def create_practice_set(
    body: PracticeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PracticeSetRead:
    if not (body.topic or body.document_id or body.conversation_id):
        raise HTTPException(
            status_code=422,
            detail="give me a topic, a document, or a conversation to build questions from",
        )
    category = ensure_category(db, user, body.category) if body.category else None
    try:
        ps = generate_practice_set(
            db, user,
            topic=body.topic, document_id=body.document_id,
            conversation_id=body.conversation_id, category=category,
            study_level=body.study_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _set_read(db, user.id, ps)


@router.get("", response_model=list[PracticeSetSummary])
def list_practice_sets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 50,
) -> list[PracticeSetSummary]:
    q_count = (
        select(Question.practice_set_id, func.count(Question.id).label("n"))
        .group_by(Question.practice_set_id)
        .subquery()
    )
    a_count = (
        select(
            Attempt.practice_set_id,
            func.count(Attempt.id).label("answered"),
            func.count(Attempt.id).filter(Attempt.correct.is_(True)).label("correct"),
        )
        .where(Attempt.user_id == user.id)
        .group_by(Attempt.practice_set_id)
        .subquery()
    )
    rows = db.execute(
        select(PracticeSet, q_count.c.n, a_count.c.answered, a_count.c.correct)
        .outerjoin(q_count, q_count.c.practice_set_id == PracticeSet.id)
        .outerjoin(a_count, a_count.c.practice_set_id == PracticeSet.id)
        .where(PracticeSet.user_id == user.id)
        .order_by(PracticeSet.created_at.desc())
        .limit(min(limit, 200))
    ).all()
    return [
        PracticeSetSummary(
            id=ps.id, topic=ps.topic, category=ps.category, study_level=ps.study_level,
            source=ps.source, created_at=ps.created_at,
            question_count=int(n or 0), answered=int(ans or 0), correct=int(cor or 0),
        )
        for ps, n, ans, cor in rows
    ]


@router.get("/{set_id}", response_model=PracticeSetRead)
def get_practice_set(
    set_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PracticeSetRead:
    return _set_read(db, user.id, _owned_set(db, user, set_id))


@router.post("/{set_id}/questions/{index}/grade", response_model=GradeResponse)
def grade(
    set_id: str,
    index: int,
    body: GradeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GradeResponse:
    ps = _owned_set(db, user, set_id)
    question = next((q for q in ps.questions if q.index == index), None)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    attempt = grade_attempt(
        db, user, question, answer=body.answer, option_index=body.option_index
    )
    return GradeResponse(
        attempt=_attempt_read(attempt),
        answer=question.answer,
        rubric=question.rubric,
        model=ps.model,
    )


@router.post("/{set_id}/questions/{index}/grade-upload", response_model=GradeResponse)
async def grade_upload(
    set_id: str,
    index: int,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GradeResponse:
    """Grade a photo / PDF of the student's handwritten working."""
    ps = _owned_set(db, user, set_id)
    question = next((q for q in ps.questions if q.index == index), None)
    if question is None:
        raise HTTPException(status_code=404, detail="question not found")
    if getattr(question, "answer_mode", "text") != "text_or_upload":
        raise HTTPException(status_code=422, detail="this question takes a typed answer")

    name = file.filename or "answer"
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in _ANSWER_UPLOAD_EXT:
        raise HTTPException(
            status_code=415, detail=f"upload an image or PDF (got {ext or 'unknown'})"
        )
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file too large")

    from app.services.vision import transcribe_work

    try:
        prompt = question.prompt + (f"\n\n(Student note: {note})" if note else "")
        transcription, tnotes = transcribe_work(raw, name, prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if tnotes:
        transcription = f"{transcription}\n\n[reader notes: {tnotes}]"
    attempt = grade_attempt(
        db, user, question, transcription=transcription, image_path=name[:512]
    )
    return GradeResponse(
        attempt=_attempt_read(attempt),
        answer=question.answer,
        rubric=question.rubric,
        model=ps.model,
    )


@router.delete("/{set_id}")
def delete_practice_set(
    set_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    ps = _owned_set(db, user, set_id)
    db.delete(ps)
    db.commit()
    return {"deleted": set_id}
