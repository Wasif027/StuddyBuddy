"""Progress dashboard aggregations — streaks, per-subject trends, tier breakdowns.

Philosophy throughout: an unanswered question counts as incorrect, not as a
gap. A practice set you generated but never started is real information (a
0/N result), and hiding it would make "overall accuracy" and a subject's
trend line lie by omission.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.orm import Attempt, Category, Document, Note, PracticeSet, User
from app.models.schemas import CategoryProgress, ProgressResponse, SetTrendPoint


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
    sets = list(
        db.execute(
            select(PracticeSet)
            .where(PracticeSet.user_id == user.id)
            .options(selectinload(PracticeSet.questions))
            .order_by(PracticeSet.created_at)
        ).scalars().all()
    )

    notes = int(db.execute(
        select(func.count(Note.id)).where(Note.user_id == user.id)
    ).scalar_one())
    cats = db.execute(select(Category).where(Category.user_id == user.id)).scalars().all()
    cat_label = {c.slug: c.label for c in cats}
    cat_docs: dict[str, int] = defaultdict(int)
    for slug, n in db.execute(
        select(Document.category, func.count(Document.id))
        .where(Document.user_id == user.id).group_by(Document.category)
    ).all():
        cat_docs[slug or "general"] = int(n)
    docs = sum(cat_docs.values())  # same total, one fewer round trip to a remote DB

    if not sets:
        return ProgressResponse(
            documents=docs, notes=notes,
            by_category=[
                CategoryProgress(category=c.slug, label=c.label, doc_count=cat_docs.get(c.slug, 0))
                for c in cats if cat_docs.get(c.slug, 0)
            ],
        )

    # Latest attempt per question (a question can be re-answered; the most
    # recent grade is what counts), then grouped by the set it belongs to.
    all_attempts = list(
        db.execute(
            select(Attempt).where(Attempt.user_id == user.id).order_by(Attempt.created_at)
        ).scalars().all()
    )
    latest_by_qid: dict[str, Attempt] = {}
    for a in all_attempts:
        if a.question_id:
            latest_by_qid[a.question_id] = a
    by_set: dict[str, dict[str, Attempt]] = defaultdict(dict)
    for qid, a in latest_by_qid.items():
        if a.practice_set_id:
            by_set[a.practice_set_id][qid] = a

    total_questions = 0
    total_correct = 0
    incomplete_sets = 0
    by_tier_scores: dict[str, list[float]] = defaultdict(list)
    by_day: dict[date, list[float]] = defaultdict(list)
    by_cat_sets: dict[str, list[PracticeSet]] = defaultdict(list)
    by_cat_tier: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for ps in sets:
        qn = len(ps.questions)
        total_questions += qn
        attempts_here = by_set.get(ps.id, {})
        correct_here = sum(1 for a in attempts_here.values() if a.correct)
        total_correct += correct_here
        if len(attempts_here) < qn:
            incomplete_sets += 1

        cat_key = ps.category or "general"
        by_cat_sets[cat_key].append(ps)

        for q in ps.questions:
            a = attempts_here.get(q.id)
            if a:
                by_tier_scores[q.tier.value].append(a.score)
                by_cat_tier[cat_key][q.tier.value].append(a.score)
                by_day[a.created_at.date()].append(a.score)

    current, longest = _streaks(list(by_day.keys()))

    cat_progress: list[CategoryProgress] = []
    seen_cats = set(by_cat_sets) | {c.slug for c in cats if cat_docs.get(c.slug)}
    for slug in sorted(seen_cats):
        cat_sets = by_cat_sets.get(slug, [])
        trend: list[SetTrendPoint] = []
        solved = 0
        for ps in cat_sets:
            qn = len(ps.questions)
            attempts_here = by_set.get(ps.id, {})
            correct_here = sum(1 for a in attempts_here.values() if a.correct)
            if qn and len(attempts_here) >= qn:
                solved += 1
            trend.append(SetTrendPoint(
                set_id=ps.id, created_at=ps.created_at.isoformat(),
                correct=correct_here, total=qn,
                accuracy=round(correct_here / qn, 3) if qn else 0.0,
            ))
        tier_acc = {t: round(sum(v) / len(v), 3) for t, v in by_cat_tier.get(slug, {}).items()}
        cat_progress.append(CategoryProgress(
            category=slug, label=cat_label.get(slug, slug.replace("-", " ").title()),
            total_sets=len(cat_sets), solved_sets=solved,
            doc_count=cat_docs.get(slug, 0), by_tier=tier_acc, trend=trend,
        ))

    return ProgressResponse(
        total_questions=total_questions,
        total_correct=total_correct,
        current_streak=current,
        longest_streak=longest,
        total_sets=len(sets),
        incomplete_sets=incomplete_sets,
        by_tier={t: round(sum(v) / len(v), 3) for t, v in by_tier_scores.items()},
        by_category=cat_progress,
        documents=docs,
        notes=notes,
    )
