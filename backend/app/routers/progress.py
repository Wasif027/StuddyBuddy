"""Progress dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import User
from app.models.schemas import ProgressResponse
from app.services.progress import build

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("", response_model=ProgressResponse)
def get_progress(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProgressResponse:
    return build(db, user)
