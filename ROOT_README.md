# Flask to FastAPI Migration Study — Receipt Verification Service

An Accenture internship project that implements the same Receipt Verification REST API twice — once in Flask and once in FastAPI — connected to the same MongoDB Atlas cluster, to compare architecture, developer experience, and measured performance under concurrent load.

**Result:** FastAPI handled ~80% more requests per second with ~68% lower average latency under identical load (Locust benchmark, 20 concurrent users).

---

## Project structure

```
project-root/
├── flask-app/          Flask implementation (PyMongo, Gunicorn)
├── fastapi-app/        FastAPI implementation (Motor async, Uvicorn)
├── benchmarks/         Locust load-testing suite (runs against both)
├── docker-compose.yml  Starts both services together (requires Docker)
└── README.md           This file
```

Each folder has its own README with full details:
- [Flask app →](flask-app/README.md)
- [FastAPI app →](fastapi-app/README.md)
- [Benchmarks →](benchmarks/README.md)

---

## Prerequisites

- **Python 3.12 or later** — download from [python.org](https://python.org). During install on Windows, tick **"Add Python to PATH"**.
- **Git** — download from [git-scm.com](https://git-scm.com)
- **MongoDB Atlas account** — free at [cloud.mongodb.com](https://cloud.mongodb.com)
- A terminal — **Git Bash** (installed with Git) is recommended on Windows

Verify before continuing:
```bash
python --version      # should show 3.12 or higher
git --version
```

---

## Quick start (Windows — Git Bash)

### Step 1 — Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### Step 2 — Set up the Flask app

```bash
cd flask-app
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in three values:
```
MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
API_KEY=any-secret-string-you-choose
JWT_SECRET_KEY=any-long-random-string
```

Run:
```bash
python app.py
```

Flask is now running at `http://localhost:5000`

### Step 3 — Set up the FastAPI app (new terminal)

```bash
cd fastapi-app
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and use the **same values** as the Flask `.env` — both apps share one Atlas cluster.

Run:
```bash
python -m uvicorn app:app --reload --port 8000
```

FastAPI is now running at `http://localhost:8000`
Swagger UI (interactive docs): `http://localhost:8000/docs`

---

## MongoDB Atlas setup (if you haven't already)

1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) → create a free M0 cluster
2. **Database Access** → Add New User → set username + password
3. **Network Access** → Add IP Address → Add Current IP (or `0.0.0.0/0` for development)
4. **Connect** → Drivers → copy the connection string → replace `<password>` → paste as `MONGODB_URI` in both `.env` files

> ⚠️ The `.env` files are gitignored — they will never be pushed to GitHub. Never put your real password in `.env.example`.

---

## Running the tests

```bash
# In the flask-app folder with venv active:
python -m pytest tests/ -v
# Expected: 32 passed

# In the fastapi-app folder with venv active:
python -m pytest tests/ -v
# Expected: 35 passed
```

Tests mock MongoDB entirely — no live Atlas connection needed.

---

## Running the benchmark

Both apps must be running first (Steps 2 and 3 above), with rate limiting disabled:

Set `RATE_LIMIT_ENABLED=false` in **both** `.env` files, then restart both apps.

```bash
# From the project root, with locust installed:
pip install -r benchmarks/requirements.txt
python benchmarks/run_benchmarks.py
```

Results are saved to `benchmarks/results/locust/`.

---

## Environment variables reference

All variables go in `.env` (copied from `.env.example`). Both apps use the same format.

| Variable | Required | Description |
|---|---|---|
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `API_KEY` | No | Secret for X-API-Key header auth (default: `change-me`) |
| `JWT_SECRET_KEY` | No | Secret for signing JWT tokens |
| `RATE_LIMIT_ENABLED` | No | Set `false` before benchmarking (default: `true`) |
| `RATE_LIMIT_PER_MINUTE` | No | Request limit per IP (default: `30`) |
| `JWT_EXPIRY_MINUTES` | No | JWT token lifetime in minutes (default: `60`) |

---

## Note on Gunicorn and Docker

The Flask app's `requirements.txt` and `Dockerfile` reference Gunicorn (the production WSGI server). Gunicorn depends on `fcntl`, a Unix/Linux-only system module that has no Windows implementation — it cannot run on Windows regardless of Docker availability. For local development on Windows, `python app.py` (Flask's built-in dev server) is used instead. Gunicorn is only relevant inside a Linux Docker container or a Linux server deployment.

FastAPI uses Uvicorn, which runs natively on Windows with no such restriction.
