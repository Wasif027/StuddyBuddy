"""Download study content as PDF or Markdown."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Attempt, PracticeSet, User
from app.models.schemas import ExportRequest
from app.services.export import markdown_to_pdf, to_markdown_file

router = APIRouter(prefix="/export", tags=["export"])

_TIER_LABEL = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "brutal": "Very hard"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "studybuddy"


def _deliver(fmt: str, title: str, markdown: str) -> Response:
    base = _slug(title)
    if fmt == "md":
        return Response(
            content=to_markdown_file(title, markdown),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{base}.md"'},
        )
    try:
        pdf = markdown_to_pdf(title, markdown)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"couldn't render the PDF: {exc}") from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{base}.pdf"'},
    )


@router.post("")
def export_markdown(
    body: ExportRequest, _user: User = Depends(get_current_user)
) -> Response:
    if not body.markdown.strip():
        raise HTTPException(status_code=422, detail="nothing to export")
    return _deliver(body.format, body.title, body.markdown)


@router.post("/practice/{set_id}")
def export_practice_set(
    set_id: str,
    fmt: str = "pdf",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    ps = db.execute(
        select(PracticeSet)
        .where(PracticeSet.id == set_id, PracticeSet.user_id == user.id)
        .options(selectinload(PracticeSet.questions))
    ).scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="practice set not found")
    attempts = {
        a.question_id: a
        for a in db.execute(
            select(Attempt).where(Attempt.user_id == user.id, Attempt.practice_set_id == set_id)
        ).scalars().all()
        if a.question_id
    }

    lines = [f"_{ps.study_level} · {len(ps.questions)} questions_", ""]
    for q in ps.questions:
        at = attempts.get(q.id)
        lines.append(f"## {q.index + 1}. {_TIER_LABEL.get(q.tier.value, q.tier.value)}")
        lines.append("")
        lines.append(q.prompt)
        if q.options_json:
            lines.append("")
            for k, opt in enumerate(q.options_json):
                lines.append(f"- {chr(65 + k)}. {opt}")
        lines.append("")
        if at:
            lines.append(f"**Your answer:** {at.user_answer or '(blank)'}")
            lines.append(f"**Score:** {round(at.score * 100)}%  ·  {at.feedback}")
        lines.append(f"**Answer:** {q.answer}")
        if q.rubric:
            lines.append(f"**Notes:** {q.rubric}")
        lines.append("")
        lines.append("---")
        lines.append("")

    fmt = "md" if fmt == "md" else "pdf"
    return _deliver(fmt, f"Practice — {ps.topic}", "\n".join(lines))
