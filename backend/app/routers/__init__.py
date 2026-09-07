"""Routers package."""

from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.conversations import router as conversations_router
from app.routers.documents import router as documents_router
from app.routers.health import router as health_router
from app.routers.retrieval import router as retrieval_router
from app.routers.suggestions import router as suggestions_router

__all__ = [
    "auth_router",
    "categories_router",
    "conversations_router",
    "documents_router",
    "health_router",
    "retrieval_router",
    "suggestions_router",
]
