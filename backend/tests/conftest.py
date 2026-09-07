"""Shared test fixtures.

Unit tests (chunking, fusion, tools, embeddings) need no services. API tests
require a Postgres+pgvector instance reachable at ``DATABASE_URL`` and are
skipped otherwise.
"""

from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SEED_ON_STARTUP", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("CACHE_ENABLED", "false")
os.environ.setdefault("OTEL_CONSOLE_EXPORT", "false")
os.environ.setdefault("LLM_PROVIDER", "offline")
os.environ.setdefault("EMBEDDING_PROVIDER", "deterministic")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://ekdp:ekdp@localhost:5432/ekdp_test"
)


def _db_available() -> bool:
    try:
        from app.core.database import ping

        return ping()
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres/pgvector not reachable")


@pytest.fixture(scope="session")
def app_client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.core.database import init_db
    from app.main import app

    init_db()
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def auth(app_client):
    """A fresh registered user; returns (client, headers, user)."""
    username = f"u_{uuid.uuid4().hex[:10]}"
    res = app_client.post(
        "/api/v1/auth/register", json={"username": username, "password": "password123"}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    return app_client, headers, body["user"]
