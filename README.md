# Groundwork

*An enterprise knowledge & decision platform.*

Sign in, upload the files a business actually runs on — **PDF, Word, Excel,
PowerPoint** (Google Sheets/Slides: use *File → Download*) — then ask questions
in natural language. Every answer comes back with:

- **an answer** grounded strictly in *your* documents,
- **inline citations** (`[1]`, `[2]`) you click to jump to the exact passage,
- **a confidence score** and label (`high` / `medium` / `low` / `insufficient`),
- **the source passages** with per-retriever scores (vector / keyword),
- **suggested next steps** — 0–4 concrete actions the answer implies, which you
  **accept / reject / mark already done**. Nothing is executed; it's a decision
  log. Reject one and the model proposes a different angle; every suggestion
  you've ever been given lives in a searchable history that links back to the
  chat message it came from.

**Query planning** picks the strategy per question:

| Question | Strategy |
| -------- | -------- |
| "what's the returns window?" | pinpoint passage retrieval |
| "summarise the monthly review deck" (or the ✦ button) | whole-document read |
| "key points across all my documents" | wide, diversified scan |
| "which candles are sold at a loss?" over a spreadsheet | **text-to-SQL** — the model writes a read-only `SELECT`, it runs against your sheets, and the **result table + the exact query** are shown in the reference panel |

**Spreadsheets are data, not prose.** Totals, per-group aggregates, rankings,
margins, trends, "which X is most/least …", multi-sheet joins — all computed and
verifiable, with a chart when the shape fits. **Decks** are summarised slide by
slide, and the data-rich slides (charts, tables, dense figures) are surfaced with
their slide numbers.

Plus **compare mode**: tick 2+ documents and the answer explicitly contrasts
them ("the 2024 policy requires manager approval [1]; the 2026 policy requires VP
approval [2]").

Not a "PDF chatbot" — a retrieval + analytics + decision layer over your business
knowledge.

---

## The workspace

```
┌──────────────┬────────────────────────────────────┬────────────────────────┐
│ CHATS        │            CONVERSATION             │  GROUNDING / NEXT STEPS │
│ (auto-hide,  │                                    │                        │
│  resizable)  │  You: a customer says their candle │        ◔  82           │
│              │       arrived smashed — what do I   │    High confidence     │
│ + New chat   │       do?                          │  ───────────────────   │
│ · Returns Q  │                                    │  Next steps · 3        │
│ · May sales  │  Offer a free replacement or a     │  ○ Email the customer  │
│              │  full refund [1]. Ask for a photo  │    offering a refund   │
│ ─────────    │  so we can claim it back [2].      │    [Accept][Reject]    │
│ Knowledge    │                                    │      [Already done]    │
│ base         │  ● High confidence · 2 cited       │  ○ Ask for a photo     │
│ 📄 Returns   │  gemini-flash-lite · 4.1s          │  ○ Log the breakage    │
│ 📊 Orders    │                                    │  ───────────────────   │
│ [+ Add doc]  │  [ ask… ]  Skip-cache               │  [1] Returns policy p.1│
└──────────────┴────────────────────────────────────┴────────────────────────┘
```

Warm-charcoal / ochre theme (light + dark), Geist type, ⌘K palette, streamed
answers, auto-hiding + drag-resizable side panels.

---

## Stack

| Layer          | Technology                                                              |
| -------------- | --------------------------------------------------------------------- |
| Frontend       | Next.js 14 (App Router), React 18, TypeScript (strict), Tailwind, Zustand |
| Backend        | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2                        |
| Auth           | Username + password, bcrypt hashing, JWT bearer tokens                |
| Database       | PostgreSQL 16 + **pgvector** (HNSW) + full-text search                 |
| Cache          | Redis (answer cache + rate limiting) — optional, degrades gracefully  |
| AI             | Anthropic / any OpenAI-compatible endpoint (Gemini, Groq, Ollama) / offline fallback |
| Ingestion      | `pypdf` · `python-docx` · `openpyxl` / `xlrd` · `python-pptx`          |
| Retrieval      | Hybrid (dense + sparse) · Reciprocal Rank Fusion · reranking · query planning · compare mode |
| Analytics      | **DuckDB** in-memory text-to-SQL over uploaded sheets (`pandas` frames, allowlisted read-only queries) |
| Decisions      | LLM-proposed next steps → per-suggestion accept / reject / done log with deep-linked history |
| Output         | Structured JSON (answer + citations + confidence + follow-ups + analysis block + suggestions) |
| Observability  | OpenTelemetry traces, Prometheus metrics, structured JSON logs        |
| Delivery       | Docker Compose, multi-stage images, GitHub Actions CI                 |

---

## Accounts & data

- On first visit you **create an account** (username + password — no email, this is a portfolio project).
- **Every account is its own workspace**: your documents, chats and suggestions are private to you. There is no shared corpus — a new account starts empty.
- Chats are persisted server-side; reload and your conversation history is restored. Start as many as you like, one per topic, like Claude.

---

## Run it

### One command — Docker (postgres + redis + backend + frontend + otel)

```bash
cp .env.example .env
docker compose up --build
```

| Service       | URL                            |
| ------------- | ------------------------------ |
| Frontend      | http://localhost:3000          |
| API + Swagger | http://localhost:8000/docs     |
| Health        | http://localhost:8000/health   |
| Metrics       | http://localhost:8000/metrics  |

With no keys the backend runs in **offline extractive mode**. Add a free Gemini
key (see [`backend/.env.example`](backend/.env.example)) for real model answers.
Open the frontend, create an account, add a document, ask.

### One command — local, no Docker

Needs a Postgres+pgvector database (a free [Neon](https://neon.tech) project
works — put its URL in `backend/.env`). Once:

```bash
npm install                          # root: installs `concurrently`
pip install -r backend/requirements.txt
npm --prefix frontend install
python -m app.core.database init     # create tables (run from backend/)
```

Then:

```bash
npm run dev            # backend :8000 + frontend :3000 together
```

**Windows / port 8000 blocked / spaces in the path** — use the PowerShell runner:

```powershell
./dev.ps1 -ApiPort 8001
```

**After any model / schema change**, rebuild the tables (destroys data):

```bash
cd backend && python -m app.core.database recreate
```

**Want a pre-filled demo account** for screenshots:

```bash
cd backend && python -m app.seed --user demo --password demopass1
```

**Deploying?** See [`DEPLOY.md`](DEPLOY.md) — platform-agnostic (any container
host for the API, Vercel for the web app).

---

## How a question is answered

```
question (+ conversationId?, documentId?, intent?, compareDocumentIds?)
  │
  ├─ resolve chat      : get or create the conversation, persist the user turn
  │
  ├─ contextualise    : an anaphoric follow-up ("and who books it?") folds the
  │                      recent turns into the retrieval query + synthesis prompt
  │
  ├─ plan retrieval    : classify the question →
  │     ├─ pinpoint    :   hybrid search + rerank, a few passages (default)
  │     ├─ document    :   "summarise X" / a named doc → load ALL its chunks in order
  │     ├─ overview    :   broad "key points across…" → wide scan, capped per document
  │     └─ analysis    :   analytic question + a spreadsheet in scope → text-to-SQL:
  │                          load sheets into DuckDB → LLM writes ONE read-only SELECT
  │                          → allowlist + LIMIT + timeout → narrate the result table
  │                          (+ a chart hint, + a light retrieval for supporting context)
  │
  ├─ embed             : openai-compatible | deterministic (offline)
  │
  ├─ hybrid retrieve   : scoped to THIS user (and to the compared/named documents,
  │     ├─ dense       :   or a category, if set)
  │     │  pgvector cosine, HNSW index
  │     └─ sparse      : Postgres websearch_to_tsquery + ts_rank_cd (trigram fallback)
  │     └─ fuse        : Reciprocal Rank Fusion
  │
  ├─ rerank            : blend of vector / keyword / term-coverage / heading / phrase
  │
  ├─ synthesize        : LLM with a strict JSON schema; a contrast prompt in compare mode
  │                      → { answer, citations[{marker, quote}], confidence, followUps }
  │
  ├─ score confidence  : 0.45·LLM_self + 0.40·retrieval + 0.15·citation_coverage
  │                      (clamped low when top evidence is weak → "insufficient")
  │
  ├─ suggest next steps : LLM proposes 0-4 concrete actions the answer implies
  │                       (none for a pure lookup) → Suggestion rows, decision=pending
  │
  └─ persist           : answers + suggestions + the assistant message (chat history)
```

Streaming (`stream=true`) emits SSE frames:
`start → grounding → [analysis] → token* → [suggestions] → final`.

---

## API (all under `/api/v1`, camelCase JSON; bearer token required except `/health` and `/auth/*`)

| Method & path                       | Purpose                                            |
| ----------------------------------- | ------------------------------------------------- |
| `POST /auth/register` · `POST /auth/login` | create account / sign in → `{ token, user }` |
| `GET  /auth/me`                     | current user                                      |
| `GET  /conversations`              | your chats (title, message count, last activity)  |
| `POST /conversations` · `PATCH` · `DELETE /{id}` | create / rename / delete a chat      |
| `GET  /conversations/{id}`         | one chat with its full message history            |
| `GET  /health`                     | service + dependency + model status               |
| `GET  /categories`                 | sidebar navigator (counts + status per category)  |
| `GET/POST /documents` · `GET/DELETE /documents/{id}` | your documents                   |
| `POST /documents/upload`           | upload `.pdf` `.docx` `.xlsx` / `.xls` `.pptx`     |
| `POST /query`                      | ask (JSON, or SSE when `stream=true`); accepts `conversationId`, `documentId`, `intent` (`auto` / `summary` / `analysis`), `compareDocumentIds`, `suggest` |
| `GET  /suggestions?status=`        | every next-step suggestion (history), with a `conversationDeleted` flag |
| `POST /suggestions/{id}/decide`    | `{ decision: accept \| reject \| done, note? }` — reject may return an `alternative` |

Full request/response shapes: `http://localhost:8000/docs`.

---

## Configuration

Env-driven. See [`backend/.env.example`](backend/.env.example). The switches that matter:

| Variable             | Default              | Effect                                            |
| -------------------- | -------------------- | ------------------------------------------------ |
| `JWT_SECRET`         | dev placeholder      | **set a 32+ char random value in production**     |
| `LLM_PROVIDER`       | `offline`            | `anthropic` \| `openai` \| `offline` (free)       |
| `OPENAI_BASE_URL`    | —                    | point `openai` at any compatible endpoint         |
| `EMBEDDING_PROVIDER` | `deterministic`      | `openai` for real (semantic) embeddings           |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` | —       | embeddings can use a different provider than chat  |
| `RERANK_ENABLED`     | `true`               | toggle the reranking pass                          |
| `SUGGESTIONS_ENABLED` | `true`              | generate next-step suggestions after each answer  |

**Free model options** — the `openai` provider drives any OpenAI-compatible endpoint. Set `LLM_PROVIDER=openai` plus:

| Provider | `OPENAI_BASE_URL` | `OPENAI_MODEL` | embeddings |
| -------- | ----------------- | -------------- | ---------- |
| Gemini (recommended) | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-flash-lite-latest` | `gemini-embedding-001` (same key) |
| Groq | `https://api.groq.com/openai/v1` | `openai/gpt-oss-20b` | (use Gemini or deterministic) |
| Ollama (local, no key) | `http://localhost:11434/v1` | `llama3.1` | `nomic-embed-text` |

Default `offline` mode still returns citations, confidence and passages — only
the answer *prose* is extractive rather than model-written, retrieval is
keyword-only without semantic embeddings, and spreadsheet analytics + next-step
suggestions (both need a model) are skipped gracefully.

---

## Tests & CI

```bash
cd backend && python -m pytest        # unit always; API/integration if Postgres reachable
cd frontend && npm run lint && npm run typecheck && npm run build
```

`.github/workflows/ci.yml` runs the backend suite against a
`pgvector/pgvector:pg16` service, the frontend lint/typecheck/build, then builds
the Docker images and probes `/health` on a booted stack.

---

## Project layout

```
backend/app/
  core/       config · database (pgvector, recreate) · cache (redis) · logging
              · telemetry · security (bcrypt + JWT) · deps (current-user)
  models/     orm.py — users · conversations · messages · documents · chunks
              · document_tables · document_slides · answers · suggestions
              schemas.py (Pydantic, camelCase — incl. AnalysisBlock / SuggestionRead)
  services/   embeddings · chunking · vectorstore (user-scoped hybrid) · reranker
              · parsing / xlsx_parse / pptx_parse (upload → text + tables + slides)
              · query_planner (pinpoint / document / overview / analysis routing)
              · analysis (DuckDB text-to-SQL) · llm (synthesis + SQL-gen + narration
              + next-step suggestions) · suggestions (serialiser) · rag (orchestration)
              · ingestion
  routers/    auth · conversations · health · categories · documents · retrieval
              · suggestions
  seed.py     optional demo corpus for a throwaway account
frontend/src/
  lib/        api (bearer + 401) · auth (token) · stream (SSE) · types · utils
  store/      useAuthStore · useAppStore (chats + compare) · useUIStore (panels) · useToast
  components/ auth · layout (LeftDock auto-hide, ResizeHandle, TopBar, CommandPalette)
              · sidebar (ConversationList, KnowledgeBase, IngestDialog)
              · grounding (RightPanel, PassageCard, AnalysisCard, DataTable, ResultChart)
              · suggestions (SuggestionCard) · history (SuggestionsHistory)
              · chat · ui · providers
infra/  ·  docker-compose.yml  ·  dev.ps1  ·  Makefile  ·  .github/workflows/ci.yml
```

---

## Production notes / upgrade paths

- **Migrations** — `create_all` for dev; wire Alembic for prod (`alembic` is a dependency).
- **Auth** — JWT + bcrypt are implemented and every data route is user-scoped.
  Not yet: refresh tokens, password reset, email verification, rate-limited login.
- **Reranker** — swap the heuristic in `services/reranker.py` for a hosted
  cross-encoder (Cohere Rerank, `bge-reranker`) behind the same interface.
- **Suggestions → real actions** — an accepted suggestion is just a logged
  decision today. Wiring "accepted" items to Jira / a mailer / Slack (behind the
  same accept gate) is a clean next step.
- **Tracing** — set `OTLP_ENDPOINT`; add a Tempo/Jaeger exporter to the collector.

## License

MIT — portfolio / internal-use demonstration.
