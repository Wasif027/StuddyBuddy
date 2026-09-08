"""Routers package."""

from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.conversations import router as conversations_router
from app.routers.documents import router as documents_router
from app.routers.export import router as export_router
from app.routers.health import router as health_router
from app.routers.notes import router as notes_router
from app.routers.practice import router as practice_router
from app.routers.progress import router as progress_router
from app.routers.retrieval import router as retrieval_router
from app.routers.study_guide import router as study_guide_router

__all__ = [
    "auth_router",
    "categories_router",
    "conversations_router",
    "documents_router",
    "export_router",
    "health_router",
    "notes_router",
    "practice_router",
    "progress_router",
    "retrieval_router",
    "study_guide_router",
]
