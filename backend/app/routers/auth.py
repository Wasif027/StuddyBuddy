"""Authentication — register, login, current user, profile."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.crypto import encrypt_secret
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.orm import User
from app.models.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    SetApiKeyRequest,
    UserRead,
    UserUpdate,
)
from app.services.catalog import seed_default_categories

router = APIRouter(prefix="/auth", tags=["auth"])

_LEVELS = {
    "year-8", "middle-school", "gcse", "high-school", "a-level", "ib",
    "undergraduate", "bachelors",
}


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(token=create_access_token(user.id), user=UserRead.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    username = body.username.strip()
    exists = db.execute(
        select(User.id).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="username already taken")
    level = (body.study_level or "high-school").strip().lower()
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or "").strip() or None,
        study_level=level if level in _LEVELS else "high-school",
    )
    db.add(user)
    db.flush()
    seed_default_categories(db, user)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.execute(
        select(User).where(func.lower(User.username) == body.username.strip().lower())
    ).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="incorrect username or password")
    return _auth_response(user)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
def update_me(
    body: UserUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> UserRead:
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
    if body.study_level is not None:
        level = body.study_level.strip().lower()
        if level not in _LEVELS:
            raise HTTPException(status_code=422, detail=f"study_level must be one of {sorted(_LEVELS)}")
        user.study_level = level
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


@router.put("/api-key", response_model=UserRead)
def set_api_key(
    body: SetApiKeyRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> UserRead:
    key = (body.api_key or "").strip()
    user.custom_llm_api_key_enc = encrypt_secret(key) if key else None
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)
