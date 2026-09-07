# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Multi-stage build for the backend. Stage 1 installs wheels; stage 2 is a
# slim non-root runtime.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder /root/.local /home/app/.local
COPY --chown=app:app . .
RUN chown -R app:app /home/app/.local

USER app
EXPOSE 8000
# Most hosts inject $PORT; fall back to 8000 locally.
ENV PORT=8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/health').status==200 else 1)"

# --proxy-headers + trust all forwarded-for hops: the platform's LB terminates TLS.
# Run `python -m app.core.database init` once before first boot (AUTO_MIGRATE=false in prod).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
