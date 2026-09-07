# Deploying

Platform-agnostic. The backend is a standard container (any host that runs a
Docker image + injects `$PORT` — Render, Railway, Fly, Cloud Run, a VPS). The
frontend is a Next 14 app (Vercel, or its own container via `output: "standalone"`).

```
browser ──▶ frontend (same-origin /api/v1/*) ──▶ backend ──▶ Postgres (Neon) + Redis (optional)
```

---

## 1. Database — Neon (or any Postgres 15+ with pgvector)

1. Create a Neon project. In **Connection Details** copy the **Pooled** connection
   string.
2. Use it as `DATABASE_URL` **as-is** — the app coerces `postgres://` /
   `postgresql://` to the `postgresql+psycopg://` driver form and appends
   `sslmode=require` for `*.neon.tech` automatically.
3. `pg_trgm` and `vector` extensions are created automatically by
   `database init` (step 3 below) — no manual SQL needed.
4. Leave autoscaling on / suspend enabled — this app has no background jobs, so
   the DB sleeps between sessions and free compute-hours are a non-issue. Do **not**
   pin compute always-on.

## 2. Backend

**Build:** `docker build -t groundwork-api ./backend`

**Environment** (see `backend/.env.example` for the full list):

| Var | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `JWT_SECRET` | 48+ random chars — `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | the pooled URL from step 1 |
| `AUTO_MIGRATE` | `false` |
| `TRUST_PROXY` | `true` |
| `CORS_ORIGINS` | the frontend's deployed origin, e.g. `https://groundwork.vercel.app` |
| `LLM_PROVIDER` + `OPENAI_*` / `EMBEDDING_*` | your Gemini (or other) keys — or leave `LLM_PROVIDER=offline` for extractive-only |
| `CACHE_ENABLED` | `false` unless you also set `REDIS_URL` (the app degrades cleanly without Redis) |
| `RATE_LIMIT_PER_MINUTE` | `30` is fine; raise if you expect concurrent demo users |

**Release step (run once, and after any schema change):**

```bash
python -m app.core.database init
```

This creates missing tables + the `suggestions.kind` / `ix_chunks_document_id`
additions. It is idempotent and non-destructive. (`recreate` drops all data — do
not run it in prod.)

**Start command** is baked into the image:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`

**Health check:** `GET /health` → `{"ok": true}`.

## 3. Frontend

**Vercel:** import the repo, then:

- **Root Directory:** `frontend` (Settings → General). In a monorepo Vercel often
  leaves the framework as "Other" — set **Framework Preset: Next.js** explicitly or
  the build looks for `public/` and fails.
- **Deployment Protection:** off. It defaults to on (Vercel Authentication), which
  makes the site 401 for anyone not logged into your Vercel account — kills a
  public demo link.

Set one env var:

| Var | Value |
| --- | --- |
| `API_PROXY_TARGET` | the backend's public URL, e.g. `https://groundwork-api.onrender.com` |

The browser only ever calls the frontend's own origin (`/api/v1/*`); the Next
server proxies to `API_PROXY_TARGET`, so SSE streams cleanly and there is no
browser CORS. `NEXT_PUBLIC_API_BASE_URL` is **not** needed with this setup.

**Own container instead:** `docker build ./frontend` (uses `output: "standalone"`),
pass `API_PROXY_TARGET` at runtime.

## 4. Smoke test

```bash
curl https://<api>/health                      # {"ok": true}
curl https://<api>/openapi.json | grep api/v1  # routes present
```

Then in the browser: open the frontend → **register** → **Add document**
(`sample-docs/`) → ask a question → confirm the answer has `[1]` citations and the
grounding panel populates.

## 5. Free-tier behaviour to expect

- **First request after idle is slow (~10–30s).** Neon suspends the DB after ~5
  min and free API hosts (Render/Fly) spin down after ~15 min. The first click
  wakes both; every request after that is fast until it idles again. Do not add a
  keep-warm ping — that runs the DB 24/7 and burns the free compute allowance.
- **LLM:** the Gemini free tier is ~1,500 req/day and ~15 req/min. A demo won't
  touch the daily cap; rapid-fire testing can hit the per-minute one (the app
  retries). If the daily quota is exhausted the app falls back to offline
  extractive answers — retrieval + citations still work, analytics don't.
- **Gemini free-tier prompts may be used by Google to improve their models** — the
  prompt includes the uploaded document text. Don't put anything real in the
  hosted demo; the sample corpus is fine.

## 6. Rollback

Redeploy the previous image. This release adds only an **additive** column
(`suggestions.kind`, default `'external'`) and an index — an older build runs
against the newer schema without changes. No down-migration needed.
