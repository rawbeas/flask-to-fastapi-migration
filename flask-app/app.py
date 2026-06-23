"""
app.py — Entry point for the Flask Receipt Verification Service.

Endpoints
---------
  GET  /health          → service status (no auth required)
  POST /upload-receipt  → upload a receipt image, returns receipt_id
  POST /extract         → extract merchant / date / amount from a receipt
  POST /validate        → validate a receipt, returns status + confidence

Auth
----
  All POST endpoints require  X-API-Key: <your-key>  header.

Run locally
-----------
  python app.py
"""

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Flask, Response, g, has_request_context, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from config.settings import Config
from services.receipt_service import extract_receipt, validate_receipt
from services.storage import save_receipt
from utils.file_validation import validate_file


# ─── Logging ──────────────────────────────────────────────────────────────────

class _RequestIdFilter(logging.Filter):
    """Injects the current request ID into every log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.request_id = getattr(g, "request_id", "no-id")
        else:
            record.request_id = "-"
        return True


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] [req=%(request_id)s] %(name)s — %(message)s"
    ))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger(__name__)


# ─── Monitoring — Prometheus metrics ──────────────────────────────────────────
# Module-level (not per-app-instance) — Prometheus client registers metrics
# globally, so these are defined once and reused across create_app() calls.

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


# ─── Background task helper ──────────────────────────────────────────────────

def _post_upload_housekeeping(receipt_id: str, filename: str) -> None:
    """
    Runs on a background thread after /upload-receipt responds.
    Stand-in for real post-upload work (e.g. notifying the ML pipeline,
    sending a webhook, cleanup of temp files, etc).
    """
    logger.info("[background] Post-upload housekeeping done — receipt_id=%s  filename=%s",
                 receipt_id, filename)


# ─── Rate limiter ─────────────────────────────────────────────────────────────
# Module-level instance, attached via init_app() — the standard Flask
# extension pattern. Creating Limiter(app=app) *inside* create_app() causes
# "weakly-referenced object no longer exists" errors once create_app()
# returns, because the route decorators hold a weakref to the local instance.
limiter = Limiter(key_func=get_remote_address)


# ─── App factory ──────────────────────────────────────────────────────────────

def create_app(config_object: object = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # ── Rate limiting ──────────────────────────────────────────────────────────
    # Flask-Limiter reads these from app.config. RATELIMIT_DEFAULT applies to
    # all routes except those marked @limiter.exempt (/health, /metrics).
    # Set RATE_LIMIT_ENABLED=false in .env to turn this off (e.g. for tests).
    app.config["RATELIMIT_ENABLED"] = app.config["RATE_LIMIT_ENABLED"]
    app.config["RATELIMIT_DEFAULT"] = f"{app.config['RATE_LIMIT_PER_MINUTE']} per minute"
    limiter.init_app(app)

    # ── Per-request ID + metrics timer ────────────────────────────────────────
    @app.before_request
    def _assign_request_id() -> None:
        # Honour caller-supplied ID if present, otherwise generate a short UUID.
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        g.start_time = time.time()
        logger.info("%s %s", request.method, request.path)

    @app.after_request
    def _record_metrics(response):
        duration = time.time() - g.get("start_time", time.time())
        REQUEST_LATENCY.labels(method=request.method, endpoint=request.path).observe(duration)
        REQUEST_COUNT.labels(method=request.method, endpoint=request.path, status=response.status_code).inc()
        return response

    # ── Auth decorator — X-API-Key OR JWT Bearer ──────────────────────────────
    def require_api_key(f):
        """
        Accepts EITHER:
          • X-API-Key: <API_KEY>                  (original method)
          • Authorization: Bearer <jwt-token>     (from POST /token)
        Either is sufficient — this lets clients pick whichever auth method
        suits them (e.g. API key for service-to-service, JWT for short-lived
        sessions after a login step).
        """
        @wraps(f)
        def _decorated(*args, **kwargs):
            # 1 ── X-API-Key
            key = request.headers.get("X-API-Key", "")
            if key and key == app.config.get("API_KEY"):
                return f(*args, **kwargs)

            # 2 ── JWT Bearer token
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ").strip()
                try:
                    jwt.decode(token, app.config["JWT_SECRET_KEY"], algorithms=[app.config["JWT_ALGORITHM"]])
                    return f(*args, **kwargs)
                except jwt.ExpiredSignatureError:
                    logger.warning("Rejected request — expired JWT")
                    return jsonify({"error": "Token expired"}), 401
                except jwt.InvalidTokenError:
                    logger.warning("Rejected request — invalid JWT")
                    # fall through to generic 401 below

            logger.warning("Rejected request — no valid X-API-Key or Bearer token")
            return jsonify({"error": "Unauthorised: provide a valid X-API-Key header or Bearer token"}), 401
        return _decorated

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/health")
    @limiter.exempt
    def health():
        """Public health-check. No auth required, not rate-limited."""
        return jsonify({"status": "ok", "service": "receipt-verification"}), 200

    @app.get("/metrics")
    @limiter.exempt
    def metrics():
        """Prometheus metrics endpoint. No auth, not rate-limited (scraped frequently)."""
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    # -------------------------------------------------------------------------
    @app.post("/token")
    def issue_token():
        """
        Exchange a valid X-API-Key for a short-lived JWT.

        Request  : (no body) — X-API-Key header required
        Response : {"access_token": "...", "token_type": "bearer", "expires_in": 3600}

        Use the returned token as:  Authorization: Bearer <access_token>
        """
        key = request.headers.get("X-API-Key", "")
        if not key or key != app.config.get("API_KEY"):
            logger.warning("Rejected /token request — bad or missing X-API-Key")
            return jsonify({"error": "Unauthorised: invalid or missing X-API-Key"}), 401

        now = datetime.now(timezone.utc)
        expiry_minutes = app.config["JWT_EXPIRY_MINUTES"]
        payload = {
            "sub": "api-client",
            "iat": now,
            "exp": now + timedelta(minutes=expiry_minutes),
        }
        token = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm=app.config["JWT_ALGORITHM"])

        logger.info("Issued JWT — expires_in=%ds", expiry_minutes * 60)
        return jsonify({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expiry_minutes * 60,
        }), 200

    # -------------------------------------------------------------------------
    @app.post("/upload-receipt")
    @require_api_key
    def upload_receipt():
        """
        Accept a receipt image/PDF, store it in MongoDB (GridFS + metadata).

        Request  : multipart/form-data  key="file"
        Response : {"receipt_id": "<uuid>"}
        """
        if "file" not in request.files:
            return jsonify({"error": "No file part. Send a multipart form with key='file'"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No file selected"}), 400

        # Validate extension + size (reads bytes internally; we seek(0) before re-reading)
        error_msg = validate_file(file)
        if error_msg:
            return jsonify({"error": error_msg}), 400

        file.seek(0)
        file_bytes = file.read()
        receipt_id = save_receipt(file_bytes, file.filename, file.content_type or "application/octet-stream")

        # ── Background task demo ──────────────────────────────────────────────
        # Flask has no built-in background-task mechanism (unlike FastAPI's
        # BackgroundTasks), so a daemon thread is the standard lightweight
        # equivalent for fire-and-forget post-upload work. For real workloads
        # (e.g. triggering the ML pipeline), use Celery / RQ instead — a thread
        # is fine for quick logging/housekeeping but won't survive a worker
        # restart and isn't tracked/retried.
        threading.Thread(
            target=_post_upload_housekeeping,
            args=(receipt_id, file.filename),
            daemon=True,
        ).start()

        logger.info("Receipt uploaded — receipt_id=%s  filename=%s  size=%d bytes",
                    receipt_id, file.filename, len(file_bytes))
        return jsonify({"receipt_id": receipt_id}), 201

    # -------------------------------------------------------------------------
    @app.post("/extract")
    @require_api_key
    def extract():
        """
        Extract structured data from a previously uploaded receipt.

        Request  : {"receipt_id": "<uuid>"}
        Response : {"merchant": "...", "date": "YYYY-MM-DD", "amount": "..."}
        """
        body = request.get_json(silent=True) or {}
        receipt_id = body.get("receipt_id", "").strip()
        if not receipt_id:
            return jsonify({"error": "'receipt_id' is required in the JSON body"}), 400

        result = extract_receipt(receipt_id)
        if result is None:
            return jsonify({"error": f"receipt_id '{receipt_id}' not found"}), 404

        logger.info("Extraction done — receipt_id=%s  result=%s", receipt_id, result)
        return jsonify(result), 200

    # -------------------------------------------------------------------------
    @app.post("/validate")
    @require_api_key
    def validate():
        """
        Validate a previously uploaded receipt via the ML model.

        Request  : {"receipt_id": "<uuid>"}
        Response : {"status": "Valid|Invalid|Uncertain", "confidence": "92%"}
        """
        body = request.get_json(silent=True) or {}
        receipt_id = body.get("receipt_id", "").strip()
        if not receipt_id:
            return jsonify({"error": "'receipt_id' is required in the JSON body"}), 400

        result = validate_receipt(receipt_id)
        if result is None:
            return jsonify({"error": f"receipt_id '{receipt_id}' not found"}), 404

        logger.info("Validation done — receipt_id=%s  result=%s", receipt_id, result)
        return jsonify(result), 200

    # ── Error handlers ────────────────────────────────────────────────────────

    @app.errorhandler(404)
    def _not_found(e):
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def _method_not_allowed(e):
        return jsonify({"error": "Method not allowed on this endpoint"}), 405

    @app.errorhandler(429)
    def _rate_limited(e):
        return jsonify({"error": f"Rate limit exceeded: {e.description}"}), 429

    @app.errorhandler(Exception)
    def _unhandled(e):
        logger.exception("Unhandled exception: %s", e)
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

    return app


# ─── Module-level app instance (used by Dockerfile CMD and local run) ─────────
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)