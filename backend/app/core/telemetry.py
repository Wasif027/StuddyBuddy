"""OpenTelemetry tracing + FastAPI/SQLAlchemy/Redis instrumentation.

``setup_telemetry`` is idempotent (safe under hot-reload and tests). Call
``instrument_app(app)`` once from the app factory so request spans are emitted.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor

from app.core.config import Settings, get_settings

_INITIALISED = False


def setup_telemetry(settings: Settings | None = None) -> TracerProvider:
    global _INITIALISED
    if _INITIALISED:
        return trace.get_tracer_provider()  # type: ignore[return-value]

    settings = settings or get_settings()
    resource = Resource.create(
        {
            "service.name": settings.app_name,
            "service.version": settings.version,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint)))
    if settings.otel_console_export and not settings.otlp_endpoint:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from app.core.database import engine

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except Exception:  # pragma: no cover
        pass
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception:  # pragma: no cover
        pass

    _INITIALISED = True
    return provider


def instrument_app(app) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:  # pragma: no cover
        pass


def tracer(name: str | None = None):
    return trace.get_tracer(name or get_settings().app_name)
