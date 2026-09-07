"""Thin Redis wrapper used for answer caching and fixed-window rate limiting.

All operations degrade gracefully: if Redis is unavailable the helpers behave
as a cache miss / no-op so the API keeps working.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client = None
_unavailable = False


def get_client():
    global _client, _unavailable
    if _client is not None or _unavailable:
        return _client
    try:
        import redis

        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
        _client.ping()
    except Exception as exc:  # pragma: no cover - env dependent
        logger.warning("redis_unavailable", error=str(exc))
        _client = None
        _unavailable = True
    return _client


def ping() -> bool:
    client = get_client()
    if not client:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False


def cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    return "ekdp:" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def get_json(key: str) -> Any | None:
    if not settings.cache_enabled:
        return None
    client = get_client()
    if not client:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    if not settings.cache_enabled:
        return
    client = get_client()
    if not client:
        return
    try:
        client.set(key, json.dumps(value, default=str), ex=ttl or settings.answer_cache_ttl_seconds)
    except Exception:  # pragma: no cover
        pass


def invalidate_prefix(prefix: str) -> None:
    if not settings.cache_enabled:
        return
    client = get_client()
    if not client:
        return
    try:
        for k in client.scan_iter(match=f"{prefix}*", count=200):
            client.delete(k)
    except Exception:  # pragma: no cover
        pass


def rate_limit_hit(identity: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, remaining)."""
    client = get_client()
    if not client:
        return True, limit
    try:
        bucket = f"ekdp:rl:{identity}:{window_seconds}"
        count = client.incr(bucket)
        if count == 1:
            client.expire(bucket, window_seconds)
        remaining = max(0, limit - int(count))
        return int(count) <= limit, remaining
    except Exception:  # pragma: no cover
        return True, limit
