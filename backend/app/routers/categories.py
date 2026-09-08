"""Per-user subject categories — the left-sidebar folders."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.orm import Category, Document, User
from app.models.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.catalog import counts_by_slug, slugify

router = APIRouter(prefix="/categories", tags=["categories"])


def _to_read(cat: Category, counts: dict[str, dict[str, int]]) -> CategoryRead:
    c = counts.get(cat.slug, {})
    return CategoryRead(
        id=cat.id,
        slug=cat.slug,
        label=cat.label,
        level=cat.level,
        color=cat.color,
        is_default=cat.is_default,
        doc_count=c.get("docs", 0),
        note_count=c.get("notes", 0),
        created_at=cat.created_at,
    )


@router.get("", response_model=list[CategoryRead])
def list_categories(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[CategoryRead]:
    cats = db.execute(
        select(Category).where(Category.user_id == user.id).order_by(Category.label)
    ).scalars().all()
    counts = counts_by_slug(db, user.id)
    return [_to_read(c, counts) for c in cats]


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> CategoryRead:
    slug = slugify(body.slug or body.label)
    exists = db.execute(
        select(Category).where(Category.user_id == user.id, Category.slug == slug)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="a category with that name already exists")
    cat = Category(
        user_id=user.id, slug=slug, label=body.label.strip(),
        level=body.level or user.study_level, color=body.color,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return _to_read(cat, {})


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: str,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CategoryRead:
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id != user.id:
        raise HTTPException(status_code=404, detail="category not found")
    if body.label is not None:
        cat.label = body.label.strip()
    if body.level is not None:
        cat.level = body.level or None
    if body.color is not None:
        cat.color = body.color or None
    db.commit()
    db.refresh(cat)
    return _to_read(cat, counts_by_slug(db, user.id))


@router.delete("/{category_id}")
def delete_category(
    category_id: str,
    reassign_to: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id != user.id:
        raise HTTPException(status_code=404, detail="category not found")
    target = slugify(reassign_to) if reassign_to else None
    db.query(Document).filter(
        Document.user_id == user.id, Document.category == cat.slug
    ).update({Document.category: target}, synchronize_session=False)
    db.delete(cat)
    db.commit()
    return {"deleted": category_id, "reassigned_to": target}
