# StudyBuddy

*An adaptive AI study tutor — grounded in your own notes.*

Sign in, tell it what level you study at, and ask it to explain anything up to
undergraduate level. It pitches the explanation to you and goes **simpler**,
**deeper** or **exam-style** on request. Upload your notes, slides or a **photo**
of a page and every explanation is grounded in them with citations back to the
exact page or slide.

When you're ready to test yourself, it writes a practice set — **4 easy, 4
medium, 2 hard and 1 very hard** question at your level — and marks your answers
with feedback. It builds study guides, glossaries, concept maps and flashcards
from any material, keeps a notes / learning log, turns a photo of your timetable
into a structured schedule, and tracks your scores, streak and weak topics.

Not a "chat with a PDF" — a tutor, an assessment engine and a progress tracker
over your own study materials.

---

## What it does

| Area | |
| --- | --- |
| **Adaptive tutoring** | Explanations pitched to your study level, with four depth modes (simple / standard / in-depth / exam). Follow-up chips. Greets you and asks what you're working on. |
| **Grounded answers** | Retrieval over your uploaded materials — hybrid dense + sparse search, RRF, reranking. Inline `[n]` citations you click to jump to the source passage. A clear badge when an answer came from general knowledge instead. |
| **Practice** | Generate an 11-question set (4/4/2/1) from a topic, a material, or the current chat. MCQ / short / numeric / true-false / explain. Deterministic marking where possible, model marking with partial credit + feedback for free text. Wrong answers seed a spaced-repetition schedule. |
| **Study aids** | Per material: revision guide, glossary, one-page cheat sheet, concept map, flashcards, "most important slides". |
| **Images** | Upload a photo — a diagram (explained part by part), a worked problem (full step-by-step solution), a page of notes, or a **timetable** (parsed into a day-by-day routine note). |
| **Notes** | Save any explanation from chat, keep a learning log, edit in place, "quiz me on this note". |
| **Progress** | Accuracy over time, study streak, per-difficulty breakdown, weak-topic detection with one-click practice, per-subject exam-readiness. |
| **Organisation** | Per-user subjects you can add and rename, each with its own level override. |

---

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 14 (App Router), React 18, TypeScript (strict), Tailwind, Zustand |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 |
| Auth | Username + password, bcrypt, JWT bearer |
| Database | PostgreSQL 16 + **pgvector** (HNSW) + full-text search |
| Cache | Redis (answer cache + rate limiting) — optional, degrades gracefully |
| AI | Anthropic / any OpenAI-compatible endpoint (Gemini, Groq, Ollama) / offline fallback. Optional `HARD_MODEL` for question generation + free-text grading. Vision for image uploads. |
| Ingestion | `pypdf` · `python-docx` · `python-pptx` · `pillow` (image normalisation) |
| Retrieval | Hybrid (dense + sparse) · Reciprocal Rank Fusion · reranking · query planning · compare mode |
| Spaced repetition | SM-2 (`services/sm2.py`), the algorithm behind Anki, unit-tested |
| Observability | OpenTelemetry traces, Prometheus metrics, structured JSON logs |

Every account is its own workspace — materials, chats, notes and progress are
private to you; a new account starts empty.

---

## Run it locally

### With Docker (postgres + redis + backend + frontend)

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

### Without Docker

You need a Postgres + pgvector database — a free [Neon](https://neon.tech)
project works; put its URL in `backend/.env`. Once:

```bash
npm install                                # root: installs `concurrently`
pip install -r backend/requirements.txt
npm --prefix frontend install
cp backend/.env.example backend/.env        # then set DATABASE_URL (+ optionally a Gemini key)
cd backend && python -m app.core.database init && cd ..
```

Then:

```bash
npm run dev                                 # backend :8000 + frontend :3000 together
```

Windows / port 8000 blocked:

```powershell
./dev.ps1 -ApiPort 8001
```

With no model key the backend runs in **offline mode**: retrieval, citations and
the practice pipeline still work (template questions, keyword grading), only the
explanation prose is extractive. Add a free Gemini key (see
[`backend/.env.example`](backend/.env.example)) for real tutoring, model grading
and image understanding.

**Pre-fill a demo account** for screenshots:

```bash
cd backend && python -m app.seed --user demo --password demopass1
```

**After a schema change** (rebuilds the tables — destroys data):

```bash
cd backend && python -m app.core.database recreate
```

---

## API (all under `/api/v1`, camelCase JSON; bearer token required except `/health` and `/auth/*`)

| Method & path | Purpose |
| --- | --- |
| `POST /auth/register` · `POST /auth/login` | create account / sign in → `{ token, user }` |
| `GET /auth/me` · `PATCH /auth/me` | current user · update name / study level |
| `GET/POST/PATCH/DELETE /categories` · `/categories/{id}` | subjects |
| `GET/POST/PATCH/DELETE /conversations` · `/conversations/{id}` | chats |
| `GET/POST/DELETE /documents` · `/documents/{id}` · `POST /documents/upload` | materials (`.pdf .docx .pptx` + images) |
| `POST /query` | ask (JSON, or SSE when `stream=true`); accepts `conversationId`, `documentId`, `intent`, `explainLevel`, `compareDocumentIds` |
| `POST /study-guide` | `{ documentId, kind }` — guide / glossary / cheatsheet / concept_map / flashcards / key_slides |
| `GET/POST/DELETE /practice` · `/practice/{id}` · `POST /practice/{id}/questions/{n}/grade` | practice sets |
| `GET/POST/PATCH/DELETE /notes` · `POST /notes/from-chat` · `POST /notes/{id}/quiz` | notes |
| `GET /progress` | dashboard aggregations |

Full request/response shapes: `http://localhost:8000/docs`.

---

## How a question is answered

```
question (+ conversationId?, documentId?, intent?, explainLevel?)
  │
  ├─ meta check       : greeting / "what can you do" / "what have I uploaded" → direct reply
  ├─ resolve level    : per-turn override → subject level → account study level
  ├─ contextualise    : an anaphoric follow-up folds recent turns into the retrieval query
  ├─ plan retrieval   : pinpoint (default) | document (a named material / "summarise") |
  │                     overview (broad "key points across…")
  ├─ hybrid retrieve  : user-scoped — pgvector cosine (HNSW) + Postgres full-text, fused by RRF
  ├─ rerank           : vector / keyword / term-coverage / heading / phrase blend
  ├─ explain          : LLM, pitched to the student level + depth mode, strict JSON out
  │                     → { answer, citations[{marker, quote}], confidence, grounded, followUps }
  ├─ normalise cites  : renumber [n] in order, splice missing markers, drop strays
  └─ persist          : answer + assistant message (chat history)
```

Streaming (`stream=true`) emits SSE frames: `start → grounding → token* → final`.

---

## Tests

```bash
cd backend && python -m pytest        # unit always; API tests if Postgres reachable
cd frontend && npm run lint && npm run typecheck && npm run build
```

---

## License

MIT — portfolio / demonstration project.
