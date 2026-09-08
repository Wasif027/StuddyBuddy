"""Progress dashboard aggregations — trends, streaks, weak-topic detection."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.orm import Attempt, Category, Document, Note, PracticeSet, User
from app.models.schemas import (
    CategoryProgress,
    ProgressResponse,
    SkillStat,
    TrendPoint,
)

settings = get_settings()


def _streaks(days: list[date]) -> tuple[int, int]:
    if not days:
        return 0, 0
    s = sorted(set(days))
    longest = run = 1
    for i in range(1, len(s)):
        if (s[i] - s[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    today = datetime.now(UTC).date()
    current = 0
    if s[-1] in (today, today - timedelta(days=1)):
        current = 1
        for i in range(len(s) - 1, 0, -1):
            if (s[i] - s[i - 1]).days == 1:
                current += 1
            else:
                break
    return current, longest


def build(db: Session, user: User) -> ProgressResponse:
    attempts = list(
        db.execute(
            select(Attempt)
            .where(Attempt.user_id == user.id)
            .order_by(Attempt.created_at.desc())
            .limit(settings.progress_attempt_window)
        ).scalars().all()
    )

    docs = int(db.execute(
        select(func.count(Document.id)).where(Document.user_id == user.id)
    ).scalar_one())
    notes = int(db.execute(
        select(func.count(Note.id)).where(Note.user_id == user.id)
    ).scalar_one())
    sets = int(db.execute(
        select(func.count(PracticeSet.id)).where(PracticeSet.user_id == user.id)
    ).scalar_one())
    cats = db.execute(
        select(Category).where(Category.user_id == user.id)
    ).scalars().all()
    cat_label = {c.slug: c.label for c in cats}
    cat_docs: dict[str, int] = defaultdict(int)
    for slug, n in db.execute(
        select(Document.category, func.count(Document.id))
        .where(Document.user_id == user.id).group_by(Document.category)
    ).all():
        cat_docs[slug or "general"] = int(n)

    if not attempts:
        return ProgressResponse(
            documents=docs, notes=notes, practice_sets=sets,
            by_category=[
                CategoryProgress(category=c.slug, label=c.label, doc_count=cat_docs.get(c.slug, 0))
                for c in cats if cat_docs.get(c.slug, 0)
            ],
        )

    n = len(attempts)
    overall = sum(a.score for a in attempts) / n

    by_tier_hits: dict[str, list[float]] = defaultdict(list)
    by_day: dict[date, list[float]] = defaultdict(list)
    by_skill: dict[tuple[str, str | None], list[float]] = defaultdict(list)
    by_cat: dict[str, list[float]] = defaultdict(list)
    for a in attempts:
        by_tier_hits[a.tier].append(a.score)
        by_day[a.created_at.date()].append(a.score)
        if a.skill:
            by_skill[(a.skill, a.category)].append(a.score)
        by_cat[a.category or "general"].append(a.score)

    trend = [
        TrendPoint(date=d.isoformat(), attempts=len(v), accuracy=round(sum(v) / len(v), 3))
        for d, v in sorted(by_day.items())
    ][-30:]
    current, longest = _streaks(list(by_day.keys()))

    skills = [
        SkillStat(skill=s, category=c, attempts=len(v), accuracy=round(sum(v) / len(v), 3))
        for (s, c), v in by_skill.items()
        if len(v) >= 2
    ]
    weak = sorted(skills, key=lambda x: x.accuracy)[:6]
    strong = sorted([s for s in skills if s.accuracy >= 0.75], key=lambda x: -x.accuracy)[:6]

    cat_progress: list[CategoryProgress] = []
    seen_cats = set(by_cat) | {c.slug for c in cats if cat_docs.get(c.slug)}
    for slug in sorted(seen_cats):
        scores = by_cat.get(slug, [])
        acc = round(sum(scores) / len(scores), 3) if scores else 0.0
        d = cat_docs.get(slug, 0)
        # readiness: mostly accuracy, lifted a little by having material + practice volume
        vol = min(1.0, len(scores) / 22)  # ~2 full sets
        readiness = round(min(1.0, 0.7 * acc + 0.2 * vol + (0.1 if d else 0.0)), 3) if scores else 0.0
        cat_progress.append(
            CategoryProgress(
                category=slug, label=cat_label.get(slug, slug.replace("-", " ").title()),
                attempts=len(scores), accuracy=acc, doc_count=d, readiness=readiness,
            )
        )

    return ProgressResponse(
        total_attempts=n,
        overall_accuracy=round(overall, 3),
        current_streak=current,
        longest_streak=longest,
        study_days=sorted(d.isoformat() for d in by_day),
        trend=trend,
        by_tier={k: round(sum(v) / len(v), 3) for k, v in by_tier_hits.items()},
        weak_skills=weak,
        strong_skills=strong,
        by_category=cat_progress,
        documents=docs,
        notes=notes,
        practice_sets=sets,
    )
