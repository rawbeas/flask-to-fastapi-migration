# FastAPI Receipt Verification Service

Async FastAPI REST API — the FastAPI half of an Accenture Flask-to-FastAPI migration study.
Identical API contract to the Flask version, rebuilt using FastAPI's async patterns, Motor (async MongoDB driver), and Pydantic validation.

---

## Endpoints

Same endpoints as the Flask app — a client cannot tell which framework is responding from the API surface alone (by design, for fair benchmarking).

| Method | Endpoint          | Auth       | Description                                   |
| ------ | ----------------- | ---------- | --------------------------------------------- |
| GET    | `/health`         | None       | Liveness check                                |
| GET    | `/metrics`        | None       | Prometheus metrics                            |
| POST   | `/token`          | X-API-Key  | Get a JWT token                               |
| POST   | `/upload-receipt` | Key or JWT | Upload receipt, returns receipt_id            |
| POST   | `/extract`        | Key or JWT | Extract merchant, date, amount                |
| POST   | `/validate`       | Key or JWT | Validate receipt, returns status + confidence |

Interactive docs (Swagger UI): `http://localhost:8000/docs` — click **Authorize** once, all endpoints are testable from the browser.

---

## Local setup (Windows — Git Bash)

### 1. Enter the folder

```bash
cd fastapi-app
```

### 2. Create and activate virtual environment

```bash
python -m venv .venv
source .venv/Scripts/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ Do **not** separately install `pymongo[srv]` — Motor bundles pymongo internally. Installing separately causes version conflicts.
>
> If you see a Motor/pymongo import error on first run:
>
> ```bash
> pip uninstall motor pymongo -y
> pip install --upgrade motor
> ```

### 4. Create your .env file

```bash
cp  .env
```

Open `.env` and fill in — use the **same values** as `flask-app/.env`, both apps share one Atlas cluster:

```
MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/...
API_KEY=any-secret-string
JWT_SECRET_KEY=any-long-random-string
```

> The `.env` comments must be **plain ASCII** — no special characters like em dashes or emoji. The encoding issue is documented in the project report (Section 7.3.3).

### 5. Run the app

```bash
python -m uvicorn app:app --reload --port 8000
```

App runs at: `http://localhost:8000`
Swagger UI: `http://localhost:8000/docs`

---

## Test the endpoints

Open `http://localhost:8000/docs` in your browser.

1. Click **Authorize** (top right, lock icon)
2. Enter `change-me` in the X-API-Key field → click Authorize → Close
3. All endpoints are now ready to test with **Try it out** — no cURL needed

---

## Run tests (new terminal, venv activated)

```bash
source .venv/Scripts/activate
python -m pytest tests/ -v
```

Expected: **35 passed** — Motor is fully mocked with AsyncMock, no Atlas connection needed.

---

## Key environment variables

| Variable                | Default                  | Description                        |
| ----------------------- | ------------------------ | ---------------------------------- |
| `MONGODB_URI`           | —                        | Atlas connection string (required) |
| `API_KEY`               | `change-me`              | X-API-Key header value             |
| `JWT_SECRET_KEY`        | `change-this-jwt-secret` | JWT signing secret                 |
| `RATE_LIMIT_ENABLED`    | `true`                   | Set `false` before benchmarking    |
| `RATE_LIMIT_PER_MINUTE` | `30`                     | Requests per IP per minute         |
| `JWT_EXPIRY_MINUTES`    | `60`                     | Token lifetime                     |

---

## Project structure

```
fastapi-app/
├── app.py                  Routes, lifespan, middleware, security schemes
├── config/
│   ├── settings.py         Settings singleton loaded from .env
│   └── db.py               Motor async MongoDB connection + lazy GridFS bucket
├── services/
│   ├── storage.py          Async GridFS read/write + metadata
│   └── receipt_service.py  Async extract and validate logic
├── model/
│   └── predict.py          IDENTICAL ML plug-in contract to Flask version
├── schema/
│   ├── receipt_request.py  Pydantic request models (auto-validated)
│   └── receipt_response.py Pydantic response models (drives Swagger schema)
├── utils/
│   └── file_validation.py  File type and size checks
└── tests/
    └── test_app.py         35 unit tests, Motor mocked with AsyncMock
```

---

## Key differences from the Flask version

| Topic            | Flask               | FastAPI                    |
| ---------------- | ------------------- | -------------------------- |
| Route functions  | `def`               | `async def`                |
| MongoDB driver   | PyMongo (sync)      | Motor (async)              |
| Validation       | Manual dataclasses  | Pydantic (automatic)       |
| Auth wiring      | Custom decorator    | `Depends(require_api_key)` |
| Docs             | None (Postman/cURL) | Auto Swagger UI at `/docs` |
| Background tasks | Daemon thread       | Native `BackgroundTasks`   |
| Startup logic    | Module-level        | `lifespan` context manager |

---

## ML model handoff

`model/predict.py` is byte-for-byte identical to the Flask version. The same real model drops into both apps without any changes to either service.
