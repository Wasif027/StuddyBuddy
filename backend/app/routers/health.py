"""Liveness / readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.core import cache
from app.core.config import get_settings
from app.core.database import ping as pg_ping
from app.models.schemas import HealthResponse, ServiceStatus

settings = get_settings()
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service + dependency health")
def health() -> HealthResponse:
    pg = "up" if pg_ping() else "down"
    redis = "up" if cache.ping() else "down"
    status = "healthy" if pg == "up" else "unhealthy" if pg == "down" else "degraded"
    if status == "healthy" and redis != "up":
        status = "degraded"
    return HealthResponse(
        status=status,  # type: ignore[arg-type]
        version=settings.version,
        env=settings.app_env,
        services=ServiceStatus(postgres=pg, redis=redis),
        llm_provider=settings.llm_provider,
        llm_model=settings.active_model_name,
        llm_active=settings.llm_active,
        embedding_provider=settings.embedding_provider,
        embedding_dim=settings.embedding_dim,
    )
