"""
app.py — Entry point for the FastAPI Receipt Verification Service.

Endpoints (same as the Flask version, for parity / benchmarking)
------------------------------------------------------------------
  GET  /health          → service status (no auth required)
  POST /upload-receipt  → upload a receipt image, returns receipt_id
  POST /extract         → extract merchant / date / amount from a receipt
  POST /validate        → validate a receipt, returns status + confidence

Auth
----
  All POST endpoints require  X-API-Key: <your-key>  header
  (enforced via Depends(require_api_key)).

Swagger UI
----------
  http://localhost:8000/docs

Run locally
-----------
  uvicorn app:app --reload --port 8000
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from config.db import check_connection, metadata_collection
from config.settings import settings
from schema.receipt_request import ExtractRequest, ValidateRequest
from schema.receipt_response import (
    ErrorResponse,
    ExtractResponse,
    HealthResponse,
    TokenResponse,
    UploadResponse,
    ValidateResponse,
)
from services.receipt_service import extract_receipt, validate_receipt
from services.storage import save_receipt
from utils.file_validation import validate_file

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Monitoring — Prometheus metrics ──────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


# ─── Rate limiter ─────────────────────────────────────────────────────────────
# Set RATE_LIMIT_ENABLED=false in .env to disable entirely (e.g. for tests).
# storage_uri="memory://" is per-process — with --workers > 1 in production,
# point this at Redis so limits apply across all workers.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED,
    storage_uri=settings.RATELIMIT_STORAGE_URI,
)


# ─── Background task helper ──────────────────────────────────────────────────

def _post_upload_housekeeping(receipt_id: str, filename: str) -> None:
    """
    Runs after the response is sent (FastAPI's BackgroundTasks).
    Stand-in for real post-upload work (e.g. notifying the ML pipeline,
    sending a webhook, cleanup of temp files, etc).
    """
    logger.info("[background] Post-upload housekeeping done — receipt_id=%s  filename=%s",
                 receipt_id, filename)


# ─── Lifespan — connect + create indexes on startup ──────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await check_connection()
    logger.info("✅  MongoDB Atlas — connected successfully")

    # receipt_id is looked up on every /extract and /validate call —
    # a unique index keeps those lookups fast and prevents duplicate IDs.
    await metadata_collection.create_index("receipt_id", unique=True)
    logger.info("✅  Ensured unique index on 'receipt_id'")

    yield

    # Shutdown
    from config.db import client
    client.close()
    logger.info("MongoDB connection closed")


app = FastAPI(
    title="Receipt Verification Service (FastAPI)",
    description="Async FastAPI counterpart to the Flask receipt verification service.",
    version="1.0.0",
    lifespan=lifespan,
)

# slowapi reads the limiter off app.state
app.state.limiter = limiter


# ─── Request ID logging middleware ───────────────────────────────────────────

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    start = time.time()
    logger.info("[req=%s] %s %s", request_id, request.method, request.url.path)

    response = await call_next(request)

    duration = time.time() - start
    response.headers["X-Request-ID"] = request_id
    logger.info("[req=%s] %s %s → %d (%.1fms)",
                 request_id, request.method, request.url.path,
                 response.status_code, duration * 1000)

    # ── Monitoring ────────────────────────────────────────────────────────────
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()

    return response


# ─── Auth dependency — X-API-Key OR JWT Bearer ───────────────────────────────
#
# Using fastapi.security schemes (instead of plain Header() params) gives a
# single "Authorize" button (top-right of /docs) where you enter your
# X-API-Key and/or JWT once — Swagger then attaches it to every "Try it out"
# request automatically. Plain Header() fields don't reliably get included
# in the request from Swagger's per-endpoint parameter inputs.
#
# auto_error=False on both — we want to check X-API-Key first, fall back to
# JWT, and only raise 401 ourselves if NEITHER is present/valid.
_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_key(
    x_api_key: str | None = Depends(_api_key_scheme),
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """
    Dependency — accepts EITHER:
      • X-API-Key: <API_KEY>                  (original method)
      • Authorization: Bearer <jwt-token>     (from POST /token)
    Either is sufficient. Raises 401 if neither is valid.
    Use as:  api_key: str = Depends(require_api_key)
    """
    # 1 ── X-API-Key
    if x_api_key and x_api_key == settings.API_KEY:
        return x_api_key

    # 2 ── JWT Bearer token
    if bearer:
        token = bearer.credentials
        try:
            jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            return token
        except jwt.ExpiredSignatureError:
            logger.warning("Rejected request — expired JWT")
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            logger.warning("Rejected request — invalid JWT")
            # fall through to generic 401 below

    logger.warning("Rejected request — no valid X-API-Key or Bearer token")
    raise HTTPException(status_code=401, detail="Unauthorised: provide a valid X-API-Key header or Bearer token")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    """Public health-check. No auth required, not rate-limited."""
    return HealthResponse(status="ok", service="receipt-verification")


@app.get("/metrics", tags=["health"])
async def metrics():
    """Prometheus metrics endpoint. No auth, not rate-limited (scraped frequently)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# -------------------------------------------------------------------------
@app.post(
    "/token",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    tags=["auth"],
)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def issue_token(
    request: Request,  # required by slowapi's @limiter.limit
    x_api_key: str | None = Depends(_api_key_scheme),
):
    """
    Exchange a valid X-API-Key for a short-lived JWT.

    Request  : (no body) — X-API-Key header required
    Response : {"access_token": "...", "token_type": "bearer", "expires_in": 3600}

    Use the returned token as:  Authorization: Bearer <access_token>
    """
    if not x_api_key or x_api_key != settings.API_KEY:
        logger.warning("Rejected /token request — bad or missing X-API-Key")
        raise HTTPException(status_code=401, detail="Unauthorised: invalid or missing X-API-Key")

    now = datetime.now(timezone.utc)
    expiry_minutes = settings.JWT_EXPIRY_MINUTES
    payload = {
        "sub": "api-client",
        "iat": now,
        "exp": now + timedelta(minutes=expiry_minutes),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    logger.info("Issued JWT — expires_in=%ds", expiry_minutes * 60)
    return TokenResponse(access_token=token, token_type="bearer", expires_in=expiry_minutes * 60)


# -------------------------------------------------------------------------
@app.post(
    "/upload-receipt",
    response_model=UploadResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    tags=["receipts"],
)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def upload_receipt(
    request: Request,  # required by slowapi's @limiter.limit
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Receipt image (jpg/jpeg/png) or PDF, max 5MB"),
    api_key: str = Depends(require_api_key),
):
    """
    Accept a receipt image/PDF, store it in MongoDB (GridFS + metadata).

    Response: {"receipt_id": "<uuid>"}
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    file_bytes = await file.read()

    error_msg = validate_file(file.filename, file_bytes)
    if error_msg:
        raise HTTPException(status_code=400, detail=error_msg)

    receipt_id = await save_receipt(file_bytes, file.filename, file.content_type or "application/octet-stream")

    # ── Background task demo ──────────────────────────────────────────────────
    # Runs AFTER the response is returned to the client — for real workloads
    # (e.g. kicking off the ML pipeline) use Celery/RQ for tracking + retries;
    # BackgroundTasks is fire-and-forget within this same process.
    background_tasks.add_task(_post_upload_housekeeping, receipt_id, file.filename)

    logger.info("Receipt uploaded — receipt_id=%s  filename=%s  size=%d bytes",
                receipt_id, file.filename, len(file_bytes))
    return UploadResponse(receipt_id=receipt_id)


# -------------------------------------------------------------------------
@app.post(
    "/extract",
    response_model=ExtractResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    tags=["receipts"],
)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def extract(request: Request, body: ExtractRequest, api_key: str = Depends(require_api_key)):
    """
    Extract structured data from a previously uploaded receipt.

    Request  : {"receipt_id": "<uuid>"}
    Response : {"merchant": "...", "date": "YYYY-MM-DD", "amount": "..."}
    """
    result = await extract_receipt(body.receipt_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"receipt_id '{body.receipt_id}' not found")

    logger.info("Extraction done — receipt_id=%s  result=%s", body.receipt_id, result)
    return ExtractResponse(**result)


# -------------------------------------------------------------------------
@app.post(
    "/validate",
    response_model=ValidateResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    tags=["receipts"],
)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def validate(request: Request, body: ValidateRequest, api_key: str = Depends(require_api_key)):
    """
    Validate a previously uploaded receipt via the ML model.

    Request  : {"receipt_id": "<uuid>"}
    Response : {"status": "Valid|Invalid|Uncertain", "confidence": "92%"}
    """
    result = await validate_receipt(body.receipt_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"receipt_id '{body.receipt_id}' not found")

    logger.info("Validation done — receipt_id=%s  result=%s", body.receipt_id, result)
    return ValidateResponse(**result)


# ─── Exception handlers — keep error shape {"error": "..."} same as Flask ────

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Matches Flask-Limiter's {"error": "Rate limit exceeded: ..."} shape."""
    return JSONResponse(status_code=429, content={"error": f"Rate limit exceeded: {exc.detail}"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Converts FastAPI's {"detail": "..."} into Flask-style {"error": "..."}."""
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Pydantic validation errors (e.g. missing/blank 'receipt_id') normally
    return 422. We convert to 400 + {"error": "..."} to match Flask's
    manual validation responses.
    """
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p != "body")
    message = first["msg"]
    return JSONResponse(status_code=400, content={"error": f"{field}: {message}" if field else message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)