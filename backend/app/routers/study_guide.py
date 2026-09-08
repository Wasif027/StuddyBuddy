"""Study aids generated from one uploaded material."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import User
from app.models.schemas import StudyGuideRequest, StudyGuideResponse
from app.services.study_guide import build

router = APIRouter(prefix="/study-guide", tags=["study-guide"])


@router.post("", response_model=StudyGuideResponse)
def make_study_aid(
    body: StudyGuideRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> StudyGuideResponse:
    try:
        return build(db, user, body.document_id, body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
