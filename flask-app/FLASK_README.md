# Flask Receipt Verification Service

Synchronous Flask REST API — one half of an Accenture Flask-to-FastAPI migration study.
Stores receipt images in MongoDB Atlas (GridFS), extracts data via an ML model stub, and validates receipts.

---

## Endpoints

| Method | Endpoint          | Auth       | Description                                   |
| ------ | ----------------- | ---------- | --------------------------------------------- |
| GET    | `/health`         | None       | Liveness check                                |
| GET    | `/metrics`        | None       | Prometheus metrics                            |
| POST   | `/token`          | X-API-Key  | Get a JWT token                               |
| POST   | `/upload-receipt` | Key or JWT | Upload receipt, returns receipt_id            |
| POST   | `/extract`        | Key or JWT | Extract merchant, date, amount                |
| POST   | `/validate`       | Key or JWT | Validate receipt, returns status + confidence |

---

## Local setup (Windows — Git Bash)

### 1. Enter the folder

```bash
cd flask-app
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

### 4. Create your .env file

```bash
cp .env
```

Open `.env` and fill in:

```
MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/...
API_KEY=any-secret-string
JWT_SECRET_KEY=any-long-random-string
```

### 5. Run the app

```bash
python app.py
```

App runs at: `http://localhost:5000`

> **Note on Gunicorn:** `requirements.txt` includes Gunicorn for production/Docker use, but Gunicorn cannot run on Windows (it depends on `fcntl`, a Linux-only system module). `python app.py` is the correct command for local development on Windows.

---

## Test the endpoints (Postman or cURL)

**Health check:**

```bash
curl http://localhost:5000/health
```

**Get a JWT token:**

```bash
curl -X POST http://localhost:5000/token -H "X-API-Key: change-me"
```

**Upload a receipt:**

```bash
curl -X POST http://localhost:5000/upload-receipt \
  -H "X-API-Key: change-me" \
  -F "file=@receipt.jpg"
```

**Extract data** (paste your receipt_id):

```bash
curl -X POST http://localhost:5000/extract \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{"receipt_id": "paste-id-here"}'
```

**Validate:**

```bash
curl -X POST http://localhost:5000/validate \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{"receipt_id": "paste-id-here"}'
```

---

## Run tests (new terminal, venv activated)

```bash
source .venv/Scripts/activate
python -m pytest tests/ -v
```

Expected: **32 passed** — MongoDB is fully mocked, no Atlas connection needed.

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
flask-app/
├── app.py                  Routes, auth, rate limiting, metrics
├── config/
│   ├── settings.py         Config loaded from .env
│   └── db.py               MongoDB Atlas connection (PyMongo + GridFS)
├── services/
│   ├── storage.py          GridFS read/write + metadata
│   └── receipt_service.py  Extract and validate logic
├── model/
│   └── predict.py          ML plug-in point (stub — replace with real model)
├── schema/                 Request and response dataclasses
├── utils/
│   └── file_validation.py  File type and size checks
└── tests/
    └── test_app.py         32 unit tests, MongoDB mocked
```

---

## ML model handoff

`model/predict.py` is the only file that needs to change. The contract:

```python
def predict_receipt(file_bytes: bytes, filename: str) -> dict:
    # must return: merchant, date, amount, status, confidence
```

Nothing else in the app changes when the real model replaces the stub.
