# ── Base image ────────────────────────────────────────────────────────────────
# python:3.12-slim is a minimal Debian image with Python 3.12 pre-installed.
# "slim" means no extra OS packages — smaller attack surface, faster pulls.
FROM python:3.12-slim

# ── Working directory ─────────────────────────────────────────────────────────
# All subsequent commands run from /app inside the container.
WORKDIR /app

# ── Install dependencies (COPY requirements first — layer cache trick) ────────
# By copying requirements.txt BEFORE the rest of the code, Docker can reuse
# the cached layer on rebuilds as long as requirements.txt hasn't changed.
# This means "docker build" only re-runs pip install when you add/remove deps.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# --no-cache-dir  →  don't write pip's download cache to disk (smaller image)

# ── Copy application code ─────────────────────────────────────────────────────
# Done AFTER installing deps so code changes don't invalidate the pip layer.
# .dockerignore already excludes .env, .venv/, __pycache__, .git, tests/
COPY . .

# ── Expose port ───────────────────────────────────────────────────────────────
# Documents that the container listens on port 5000.
# The actual mapping is done at runtime with  docker run -p 5000:5000
EXPOSE 5000

# ── Start command ─────────────────────────────────────────────────────────────
# Production-grade WSGI server (Deployment topic: Gunicorn + Flask vs
# Uvicorn + FastAPI). The Flask dev server (`python app.py`, used for local
# `--reload`-style development) is single-threaded and explicitly says
# "do not use in production" — gunicorn with multiple workers replaces it here.
#
#   --workers 4      → 4 separate processes handling requests (CPU-bound parallelism)
#   --bind 0.0.0.0   → listen on all interfaces so the container is reachable
#   --timeout 60     → kill a worker if a request takes > 60s (matches large file uploads)
#
# NOTE: each gunicorn worker has its own in-memory rate-limit counters
# (RATELIMIT_STORAGE_URI=memory://) — fine for this demo, but in real
# production point RATELIMIT_STORAGE_URI at a shared Redis instance so
# limits apply across all 4 workers.
#
# Secrets are injected at runtime via  docker run --env-file .env  —
# they are NEVER baked into this image.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "60", "app:app"]