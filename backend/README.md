# Backend — Groundwork

FastAPI service: account auth, per-user ingestion of business files
(PDF / Word / Excel / PowerPoint), multi-chat conversations, hybrid RAG with
structured grounded answers, **DuckDB text-to-SQL analytics over uploaded
spreadsheets**, per-slide deck extraction, a compare mode, and an AI
next-step-suggestion layer (accept / reject / done — a decision log, nothing is
executed).

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# needs Postgres+pgvector (a free Neon project works); Redis is optional
python -m app.core.database init      # create tables + indexes
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs.

After any model / schema change, rebuild (destroys data):

```bash
python -m app.core.database recreate
```

Optional throwaway demo account:

```bash
python -m app.seed --user demo --password demopass1
```

## Layout

| Path | Responsibility |
| ---- | -------------- |
| `app/core/config.py`     | typed settings (env / `.env`) — includes JWT + provider config |
| `app/core/database.py`   | engine, session, `Base`, pgvector/trigram extensions, `init`/`recreate` CLI |
| `app/core/security.py`   | bcrypt password hashing + PyJWT HS256 bearer tokens |
| `app/core/deps.py`       | `get_current_user` FastAPI dependency (401 on missing/bad token) |
| `app/core/cache.py`      | Redis answer cache + fixed-window rate limiter (degrades gracefully) |
| `app/core/telemetry.py`  | OpenTelemetry provider + FastAPI/SQLAlchemy/Redis instrumentation |
| `app/core/logging.py`    | structlog (JSON or console), trace-id enrichment |
| `app/models/orm.py`      | `users`, `conversations`, `messages`, `documents`, `chunks` (vector + tsvector), `document_tables`, `document_slides`, `answers`, `suggestions` |
| `app/models/schemas.py`  | Pydantic v2 DTOs — **camelCase** wire contract (incl. `AnalysisBlock`, `ChartSpec`) |
| `app/services/embeddings.py` | `openai` (any compatible endpoint) or deterministic offline embeddings |
| `app/services/chunking.py`   | heading-aware, token-bounded chunking (overlap never crosses a heading) |
| `app/services/parsing.py` · `xlsx_parse.py` · `pptx_parse.py` | upload → markdown text + `ParsedTable`s (typed columns, JSON-safe rows) + `ParsedSlide`s (bullets, tables, data-score) |
| `app/services/vectorstore.py`| user-scoped dense + sparse retrieval, RRF, whole-document fetch, per-doc diversify |
| `app/services/query_planner.py` | classify the question → pinpoint / document / overview / **analysis** |
| `app/services/analysis.py`   | DuckDB text-to-SQL: sheets → `pandas` frames → LLM `SELECT` → allowlist + `LIMIT` + timeout → narrate; chart hint; supporting-context retrieval |
| `app/services/reranker.py`   | lightweight cross-feature reranker (no model download) |
| `app/services/llm.py`        | structured synthesis + compare/summary/overview prompts; `generate_sql` + `narrate_analysis`; `suggest_actions` + `suggest_alternative` (anthropic / openai / offline) |
| `app/services/suggestions.py`| `Suggestion` → `SuggestionRead` serialiser (shared by rag + the router) |
| `app/services/rag.py`        | pipeline + confidence scoring + next-step suggestions + conversation/message persistence + SSE |
| `app/services/ingestion.py`  | parse (`pdf/docx/xlsx/xls/pptx`) → chunk + tables + slides → embed → store (per-user dedup on hash) |
| `app/routers/`               | `auth`, `conversations`, `health`, `categories`, `documents`, `retrieval`, `suggestions` |
| `app/seed.py`                | optional demo corpus for a throwaway account |

## Auth

- `POST /auth/register` / `POST /auth/login` → `{ token, user }`; `GET /auth/me`.
- Every data route depends on `get_current_user` and scopes its queries to that
  user — documents, chunks, conversations, answers and suggestions are all private.
- Token: HS256 JWT, `sub = user.id`, `JWT_EXPIRE_HOURS` lifetime. Set a real
  `JWT_SECRET` (32+ chars) in production — the server logs an error at startup
  if the dev placeholder is still in use under `APP_ENV=production`.

## Tests

```bash
pytest                     # unit tests always; API tests when Postgres is reachable
pytest tests/test_unit.py  # zero external dependencies
ruff check app tests
```

`tests/test_unit.py` covers chunking, embeddings, offline synthesis, the
spreadsheet / deck parsers, the SQL-injection guard, the chart heuristic and the
suggestion coercion. `tests/test_api.py` exercises the auth flow, per-user
isolation, the retrieval modes (document / overview / analysis), xlsx upload →
text-to-SQL, pptx upload → slide metadata, `.txt` rejection, the suggestion flow
(generate → accept / reject → alternative → history), suggestion-survives-chat-
delete, compare mode, conversation CRUD and the SSE stream against a real
Postgres+pgvector instance (skipped automatically otherwise). Point it at your DB
with `DATABASE_URL=... pytest`; add `LLM_PROVIDER` + a key to exercise the real
text-to-SQL and suggestion paths (both fall back gracefully without one).

## Notes

- **Schema**: `python -m app.core.database init` (or `AUTO_MIGRATE=true`) creates
  tables + the HNSW / GIN / trigram indexes for dev & CI, and drops the legacy
  `actions` table (superseded by `suggestions`; its data was all simulated). Use
  Alembic for production. `recreate` drops and rebuilds everything.
- **Suggestions**: after each answer the model proposes 0–4 next steps
  (`SUGGESTIONS_ENABLED`, needs a provider). A `reject` asks for one alternative,
  capped at `SUGGESTION_MAX_ALTERNATIVES`. Nothing is executed. A suggestion's
  `conversation_id` nulls when the chat is deleted — that's the "conversation
  deleted" signal in the history view.
- **Offline by default**: with no API keys, embeddings are deterministic and
  synthesis is extractive — the full pipeline still runs and is testable.
  Spreadsheet analytics needs a real model provider to write SQL; without one it
  returns the sheet preview and says so.
- **Analytics safety**: generated SQL must match `^(WITH|SELECT)`, is rejected on
  any DDL/DML/`PRAGMA`/file-function/`;`/comment token, is wrapped in an outer
  `LIMIT`, and runs in a worker thread with `ANALYSIS_SQL_TIMEOUT_SECONDS`
  against an in-memory DuckDB with external access disabled.
- **Rate limiting** is a Redis fixed-window counter per client IP
  (`RATE_LIMIT_PER_MINUTE`); it no-ops when Redis is down.
