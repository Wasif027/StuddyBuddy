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


def list_labels(db: Session, user: User) -> list[str]:
    """The student's own category labels — fed to auto-detect-subject prompts so
    they reuse an existing subject instead of coining a near-duplicate."""
    return list(
        db.execute(
            select(Category.label).where(Category.user_id == user.id).order_by(Category.label)
        ).scalars().all()
    )


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


def match_or_create_category(db: Session, user: User, guess: str | None) -> str | None:
    """Like :func:`ensure_category`, but for a free-text auto-detected guess
    (from vision/document classification) rather than a value the user picked
    themselves. Tries a case-insensitive LABEL match against the user's
    existing categories first — a couple of default categories (e.g. "Business
    Studies") have a hand-picked slug that a fresh ``slugify(guess)`` won't
    land on even when the guess is a perfect semantic match, which would
    otherwise silently spawn a near-duplicate category. Falls back to
    ``ensure_category`` (slug-based) when nothing matches."""
    if not guess or not guess.strip():
        return None
    needle = guess.strip().lower()
    row = db.execute(
        select(Category).where(Category.user_id == user.id, func.lower(Category.label) == needle)
    ).scalar_one_or_none()
    if row is not None:
        return row.slug
    return ensure_category(db, user, guess)


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
