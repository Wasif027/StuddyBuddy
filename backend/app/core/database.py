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


def _direct_url() -> str:
    """A schema-work URL: bypass Neon's transaction pooler (DDL / CREATE EXTENSION
    / reflection are unreliable through PgBouncer) and drop channel_binding, which
    only the pooler advertises."""
    url = settings.database_url
    url = url.replace("-pooler.", ".")
    for param in ("channel_binding=require", "channel_binding=prefer"):
        url = url.replace(f"&{param}", "").replace(f"?{param}&", "?").replace(f"?{param}", "")
    return url


@contextmanager
def _ddl_engine() -> Generator[Engine, None, None]:
    """A short-lived, unpooled engine for schema management. Every statement gets
    a fresh backend connection so extension creation and table creation can't
    trip over pooler transaction semantics."""
    ddl = create_engine(_direct_url(), poolclass=NullPool, connect_args=_connect_args, future=True)
    try:
        yield ddl
    finally:
        ddl.dispose()


def _ensure_extensions(conn) -> None:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


def _drop_legacy(conn) -> None:
    """Drop tables from the Groundwork lineage this app no longer defines. Safe on a fresh DB."""
    for tbl in ("suggestions", "actions", "document_tables"):
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))


def _ensure_columns(ddl: Engine) -> None:
    """Additive schema tweaks that ``create_all`` can't apply to existing tables.

    No Alembic; each statement is idempotent, so it's safe to run on every ``init``.
    One transaction per statement — a no-op on one must not poison the rest.
    """
    stmts = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS study_level varchar(32) NOT NULL DEFAULT 'high-school'",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS context_json jsonb NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS conversation_id varchar(36)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_llm_api_key_enc text",
        "ALTER TABLE questions ADD COLUMN IF NOT EXISTS answer_mode varchar(16) NOT NULL DEFAULT 'text'",
        "ALTER TABLE attempts ADD COLUMN IF NOT EXISTS answer_image_path varchar(512)",
        "ALTER TABLE attempts ADD COLUMN IF NOT EXISTS transcription text",
        "CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks (document_id)",
        "CREATE INDEX IF NOT EXISTS ix_documents_conversation_id ON documents (conversation_id)",
    )
    for stmt in stmts:
        try:
            with ddl.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:  # pragma: no cover
            logger.warning("ensure_columns skipped (%s): %s", stmt.split()[2], exc)


def _verify(ddl: Engine) -> None:
    from sqlalchemy import inspect

    missing = set(Base.metadata.tables) - set(inspect(ddl).get_table_names())
    if missing:
        raise RuntimeError(f"schema init did not create: {sorted(missing)}")


def init_db() -> None:
    """Create any missing tables + apply the idempotent column/index tweaks.

    Run automatically on boot when ``AUTO_MIGRATE`` is on; in production run it
    once as an explicit release step (``python -m app.core.database init``).
    """
    from app.models import orm  # noqa: F401  (register mappers)

    with _ddl_engine() as ddl:
        with ddl.begin() as conn:
            _ensure_extensions(conn)
            _drop_legacy(conn)
        Base.metadata.create_all(bind=ddl)
        _ensure_columns(ddl)
        _verify(ddl)


def recreate_all() -> None:
    """DROP every table and recreate from the models. Destroys all data.

    Run once after a schema change:  ``python -m app.core.database recreate``
    """
    from app.models import orm  # noqa: F401

    with _ddl_engine() as ddl:
        with ddl.begin() as conn:
            _ensure_extensions(conn)
        Base.metadata.drop_all(bind=ddl)
        Base.metadata.create_all(bind=ddl)
        _verify(ddl)


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
