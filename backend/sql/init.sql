-- =============================================================================
-- Enterprise AI Knowledge & Decision Platform — database bootstrap
-- =============================================================================
-- Runs once on first Postgres container start (docker-entrypoint-initdb.d).
-- Table creation itself is handled by the application (SQLAlchemy create_all in
-- dev/CI; Alembic in production). This file only ensures the required
-- extensions exist so the app can create the HNSW / GIN / trigram indexes.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector: dense similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- trigram fallback for keyword search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- convenience for manual inserts
