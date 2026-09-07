"""SQLAlchemy 2.x database layer.

Exposes the engine, a session factory, the declarative ``Base`` (with a
consistent naming convention for stable index/constraint names), and helpers
for FastAPI dependency injection and standalone scripts. Schema is managed by
``init_db()`` (``create_all`` + a small idempotent ``_ensure_columns``), not a
migration tool — see DEPLOY.md.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_engine_kwargs: dict = {"pool_pre_ping": True, "future": True, "echo": settings.debug}
if settings.app_env == "test":
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(
        pool_size=5,
        max_overflow=10,
        pool_timeout=10,
        # Neon (and most serverless PG) drop idle connections after ~5 min; recycle
        # before that so a pooled connection is never handed out already-dead.
        pool_recycle=280,
    )

# psycopg3 opens server-side prepared statements by default; Neon's transaction
# pooler can't keep them across connections, so disable them. connect_timeout
# stops a request hanging when a scaled-to-zero Neon DB is slow to wake.
_connect_args: dict = {}
if "+psycopg" in settings.database_url and "psycopg2" not in settings.database_url:
    _connect_args["prepare_threshold"] = None
    _connect_args["connect_timeout"] = 15

engine: Engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, class_=Session
)


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@event.listens_for(engine, "connect")
def _register_pgvector(dbapi_connection, _connection_record) -> None:
    """Register the ``vector`` type on each new connection.

    The extension itself is created once by ``_ensure_extensions()`` at init — we
    must not run a ``CREATE EXTENSION`` statement on every connection checkout.
    """
    try:
        from pgvector.psycopg import register_vector

        register_vector(dbapi_connection)
    except Exception as exc:  # pragma: no cover - depends on DB capabilities
        logger.warning("pgvector registration skipped: %s", exc)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session and always closing it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager: commit on success, roll back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_extensions() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


def _drop_legacy() -> None:
    """One-off cleanup of tables removed by a schema change (dev/CI only).

    `actions` (the old stubbed controlled-action rows) was replaced by
    `suggestions`. Its data was all simulated, so dropping it loses nothing real.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS actions CASCADE"))


def _ensure_columns() -> None:
    """Additive schema tweaks that ``create_all`` can't apply to existing tables.

    This project has no Alembic; each statement is idempotent so it's safe to run
    on every ``init``. Keep it small — real migrations belong in a migration tool.
    """
    stmts = (
        "ALTER TABLE suggestions ADD COLUMN IF NOT EXISTS kind varchar(16) NOT NULL DEFAULT 'external'",
        "CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks (document_id)",
    )
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception as exc:  # pragma: no cover - table may not exist yet
                logger.warning("ensure_columns skipped (%s): %s", stmt.split()[2], exc)


def init_db() -> None:
    """Create any missing tables + apply the idempotent column/index tweaks.

    Run automatically on boot when ``AUTO_MIGRATE`` is on; in production run it
    once as an explicit release step (``python -m app.core.database init``).
    """
    from app.models import orm  # noqa: F401  (register mappers)

    _ensure_extensions()
    _drop_legacy()
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def recreate_all() -> None:
    """DROP every table and recreate from the models. Destroys all data.

    Run once after a schema change:  ``python -m app.core.database recreate``
    """
    from app.models import orm  # noqa: F401

    _ensure_extensions()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def ping() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if __name__ == "__main__":  # python -m app.core.database [init|recreate]
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "recreate":
        recreate_all()
        print("database recreated (all data dropped)")
    else:
        init_db()
        print("database initialised")
