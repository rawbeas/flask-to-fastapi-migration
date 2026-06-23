# ── Base image ────────────────────────────────────────────────────────────────
# python:3.12-slim — minimal Debian image with Python 3.12 pre-installed.
FROM python:3.12-slim

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Install dependencies (COPY requirements first — layer cache trick) ────────
# Docker caches this layer. As long as requirements.txt doesn't change,
# rebuilds skip pip install entirely — much faster iteration.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────────────────
# Done AFTER installing deps so code edits don't invalidate the pip layer.
# .dockerignore excludes .env, .venv/, __pycache__, .git, tests/
COPY . .

# ── Expose port ───────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Start command ─────────────────────────────────────────────────────────────
# --host 0.0.0.0 is MANDATORY — without it uvicorn only listens inside the
# container's loopback interface and the host machine can't reach it.
#
# --workers 4  → 4 separate processes (Deployment topic: Gunicorn+Flask vs
# Uvicorn+FastAPI — this is FastAPI's equivalent of gunicorn's --workers).
# NOTE: --reload and --workers cannot be combined — --reload is for local
# dev only (see README "uvicorn app:app --reload --port 8000"); this CMD is
# the production-style config used inside Docker.
#
# Each worker has its own in-memory rate-limit counters
# (RATELIMIT_STORAGE_URI=memory://) — fine for this demo, but in real
# production point RATELIMIT_STORAGE_URI at a shared Redis instance so
# limits apply across all 4 workers.
#
# Secrets are injected at runtime via  docker run --env-file .env  —
# they are NEVER baked into this image.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]