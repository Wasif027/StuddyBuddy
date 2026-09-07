"""Structured logging setup via structlog.

``configure_logging`` is idempotent and wires stdlib ``logging`` through
structlog so every log line carries the trace/span id when one is active.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings

_CONFIGURED = False


def _add_otel_context(_logger, _method, event_dict):
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:  # pragma: no cover
        pass
    return event_dict


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_otel_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    for noisy in (
        "uvicorn.access",
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
        "openai",
        "anthropic",
        "opentelemetry",
    ):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    _CONFIGURED = True


def get_logger(name: str | None = None):
    configure_logging()
    return structlog.get_logger(name)
