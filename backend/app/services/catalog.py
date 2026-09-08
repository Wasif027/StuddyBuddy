"""User category catalogue — default subjects, slugify, get-or-create.

Categories are per-user folders (Category rows). Documents / notes / practice
sets reference them by ``slug``. New accounts get a starter set; anything the
user types that isn't a known slug is created on the fly.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.orm import Category, User

# (slug, label, colour). Deliberately broad — "education is big".
DEFAULT_CATEGORIES: list[tuple[str, str, str]] = [
    ("mathematics", "Mathematics", "#6366f1"),
    ("physics", "Physics", "#0ea5e9"),
    ("chemistry", "Chemistry", "#10b981"),
    ("biology", "Biology", "#22c55e"),
    ("computer-science", "Computer Science", "#8b5cf6"),
    ("english", "English", "#ef4444"),
    ("history", "History", "#f59e0b"),
    ("geography", "Geography", "#14b8a6"),
    ("economics", "Economics", "#eab308"),
    ("business", "Business Studies", "#f97316"),
    ("psychology", "Psychology", "#ec4899"),
    ("languages", "Languages", "#3b82f6"),
    ("general", "General", "#64748b"),
]

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    return s[:64] or "general"


def seed_default_categories(db: Session, user: User) -> None:
    existing = set(
        db.execute(select(Category.slug).where(Category.user_id == user.id)).scalars().all()
    )
    for slug, label, color in DEFAULT_CATEGORIES:
        if slug in existing:
            continue
        db.add(
            Category(
                user_id=user.id, slug=slug, label=label, color=color,
                level=user.study_level, is_default=True,
            )
        )
    db.flush()


def ensure_category(db: Session, user: User, value: str | None) -> str | None:
    """Return a category slug, creating the Category row if the value is new.
    ``value`` may be a slug or a human label."""
    if not value or not value.strip():
        return None
    slug = slugify(value)
    row = db.execute(
        select(Category).where(Category.user_id == user.id, Category.slug == slug)
    ).scalar_one_or_none()
    if row is None:
        row = Category(
            user_id=user.id, slug=slug,
            label=value.strip()[:80] if value.strip() != slug else slug.replace("-", " ").title(),
            level=user.study_level,
        )
        db.add(row)
        db.flush()
    return row.slug


def category_label(db: Session, user_id: str, slug: str | None) -> str:
    if not slug:
        return "General"
    row = db.execute(
        select(Category.label).where(Category.user_id == user_id, Category.slug == slug)
    ).scalar_one_or_none()
    return row or slug.replace("-", " ").title()


def counts_by_slug(db: Session, user_id: str) -> dict[str, dict[str, int]]:
    from app.models.orm import Document, Note

    out: dict[str, dict[str, int]] = {}
    for slug, n in db.execute(
        select(Document.category, func.count(Document.id))
        .where(Document.user_id == user_id)
        .group_by(Document.category)
    ).all():
        out.setdefault(slug or "general", {})["docs"] = int(n)
    for slug, n in db.execute(
        select(Note.category, func.count(Note.id))
        .where(Note.user_id == user_id)
        .group_by(Note.category)
    ).all():
        out.setdefault(slug or "general", {})["notes"] = int(n)
    return out
