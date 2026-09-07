"""FastAPI application factory — lifespan, middleware, routers, observability."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.cache import rate_limit_hit
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import instrument_app, setup_telemetry
from app.routers import (
    auth_router,
    categories_router,
    conversations_router,
    documents_router,
    health_router,
    retrieval_router,
    suggestions_router,
)

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_telemetry(settings)
    if settings.auto_migrate:
        try:
            from app.core.database import init_db

            init_db()
        except Exception as exc:  # pragma: no cover - depends on DB availability
            logger.error("db_init_failed", error=str(exc))
    if settings.jwt_secret.startswith("dev-insecure") and settings.app_env == "production":
        logger.error("insecure_jwt_secret_in_production — set JWT_SECRET")
    logger.info(
        "startup_complete",
        env=settings.app_env,
        llm_provider=settings.llm_provider,
        llm_active=settings.llm_active,
        embedding_provider=settings.embedding_provider,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Groundwork — hybrid RAG over business documents: cited, confidence-scored "
            "answers with source passages, spreadsheet analytics, and next-step suggestions."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-RateLimit-Remaining"],
    )
    # source_chunks payloads are the largest responses and compress ~5×; the SSE
    # stream opts out via a Content-Encoding: identity header.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    def _client_ip(request: Request) -> str:
        if settings.trust_proxy:
            fwd = request.headers.get("x-forwarded-for")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "anon"

    @app.middleware("http")
    async def observability_and_limits(request: Request, call_next):
        if settings.rate_limit_enabled and request.url.path.startswith(settings.api_v1_prefix):
            allowed, remaining = rate_limit_hit(_client_ip(request), settings.rate_limit_per_minute)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "rate limit exceeded"},
                    headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
                )
        else:
            remaining = settings.rate_limit_per_minute

        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    prefix = settings.api_v1_prefix
    app.include_router(health_router, prefix=prefix)
    app.include_router(health_router)  # also at root for load balancers
    app.include_router(auth_router, prefix=prefix)
    app.include_router(conversations_router, prefix=prefix)
    app.include_router(categories_router, prefix=prefix)
    app.include_router(documents_router, prefix=prefix)
    app.include_router(retrieval_router, prefix=prefix)
    app.include_router(suggestions_router, prefix=prefix)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    except Exception:  # pragma: no cover
        pass

    instrument_app(app)
    return app


app = create_app()
