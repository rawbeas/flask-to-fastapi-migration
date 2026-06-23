"""
tests/test_app.py — Unit tests for all four endpoints (FastAPI version).

Run
---
  python -m pytest tests/ -v

Motor is fully mocked at module level — same approach as the Flask test
suite — so these tests run without any live Atlas connection. The mock
must be in place BEFORE app.py is imported, since config/db.py validates
MONGODB_URI and creates the Motor client at import time.
"""

# ── Mock Motor BEFORE importing any app module ────────────────────────────────
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Disable rate limiting for tests — 20+ tests hit the same endpoints rapidly
# and would otherwise trip the per-minute limit. load_dotenv() does NOT
# override variables already set, so this wins even if .env sets it to true.
os.environ["RATE_LIMIT_ENABLED"] = "false"

_mock_client = MagicMock()
_mock_client.admin.command = AsyncMock(return_value={"ok": 1})
_mock_client.close = MagicMock()

_mock_metadata_collection = MagicMock()
_mock_metadata_collection.create_index = AsyncMock()

_mock_db_module = MagicMock()
_mock_db_module.client              = _mock_client
_mock_db_module.db                  = MagicMock()
_mock_db_module.get_bucket           = MagicMock(return_value=MagicMock())
_mock_db_module.metadata_collection = _mock_metadata_collection
_mock_db_module.check_connection    = AsyncMock(return_value=None)
sys.modules["config.db"] = _mock_db_module
# ─────────────────────────────────────────────────────────────────────────────

import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app

# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """
    TestClient as a context manager triggers the lifespan (startup/shutdown),
    which calls our mocked check_connection() and create_index().
    """
    with TestClient(app) as c:
        yield c


# Convenience: headers that pass API key auth
# settings.API_KEY defaults to "change-me" when .env / API_KEY is not set
AUTH = {"X-API-Key": "change-me"}
JSON = {**AUTH, "Content-Type": "application/json"}


# ─── GET /health ──────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_body(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_no_auth_required(self, client):
        """Health check must be publicly accessible."""
        resp = client.get("/health")
        assert resp.status_code == 200


# ─── POST /upload-receipt ─────────────────────────────────────────────────────

class TestUploadReceipt:

    @patch("app.save_receipt", new_callable=AsyncMock, return_value="receipt-uuid-001")
    def test_success_jpg(self, _mock, client):
        files = {"file": ("bill.jpg", io.BytesIO(b"fake-image-data"), "image/jpeg")}
        resp = client.post("/upload-receipt", headers=AUTH, files=files)
        assert resp.status_code == 201
        assert resp.json()["receipt_id"] == "receipt-uuid-001"

    @patch("app.save_receipt", new_callable=AsyncMock, return_value="id")
    def test_success_pdf(self, _mock, client):
        files = {"file": ("scan.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
        resp = client.post("/upload-receipt", headers=AUTH, files=files)
        assert resp.status_code == 201

    @patch("app.save_receipt", new_callable=AsyncMock, return_value="id")
    def test_rejects_txt(self, _mock, client):
        files = {"file": ("notes.txt", io.BytesIO(b"some text"), "text/plain")}
        resp = client.post("/upload-receipt", headers=AUTH, files=files)
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["error"]

    @patch("app.save_receipt", new_callable=AsyncMock, return_value="id")
    def test_rejects_oversized_file(self, _mock, client):
        big = b"X" * (6 * 1024 * 1024)   # 6 MB > 5 MB limit
        files = {"file": ("big.png", io.BytesIO(big), "image/png")}
        resp = client.post("/upload-receipt", headers=AUTH, files=files)
        assert resp.status_code == 400
        assert "MB" in resp.json()["error"]

    def test_no_api_key_returns_401(self, client):
        files = {"file": ("x.jpg", io.BytesIO(b"data"), "image/jpeg")}
        resp = client.post("/upload-receipt", files=files)
        assert resp.status_code == 401

    def test_wrong_api_key_returns_401(self, client):
        files = {"file": ("x.jpg", io.BytesIO(b"data"), "image/jpeg")}
        resp = client.post("/upload-receipt", headers={"X-API-Key": "wrong-key"}, files=files)
        assert resp.status_code == 401


# ─── POST /extract ────────────────────────────────────────────────────────────

_EXTRACT_RESULT = {"merchant": "ABC Store", "date": "2026-06-01", "amount": "500.00"}

class TestExtract:

    @patch("app.extract_receipt", new_callable=AsyncMock, return_value=_EXTRACT_RESULT)
    def test_success(self, _mock, client):
        resp = client.post("/extract", headers=JSON, json={"receipt_id": "some-id"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["merchant"] == "ABC Store"
        assert body["date"]     == "2026-06-01"
        assert body["amount"]   == "500.00"

    @patch("app.extract_receipt", new_callable=AsyncMock, return_value=None)
    def test_not_found(self, _mock, client):
        resp = client.post("/extract", headers=JSON, json={"receipt_id": "nonexistent"})
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_missing_receipt_id(self, client):
        resp = client.post("/extract", headers=JSON, json={})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_blank_receipt_id(self, client):
        resp = client.post("/extract", headers=JSON, json={"receipt_id": "   "})
        assert resp.status_code == 400

    def test_no_api_key(self, client):
        resp = client.post("/extract",
                           headers={"Content-Type": "application/json"},
                           json={"receipt_id": "x"})
        assert resp.status_code == 401


# ─── POST /validate ───────────────────────────────────────────────────────────

_VALIDATE_RESULT = {"status": "Valid", "confidence": "92%"}

class TestValidate:

    @patch("app.validate_receipt", new_callable=AsyncMock, return_value=_VALIDATE_RESULT)
    def test_success(self, _mock, client):
        resp = client.post("/validate", headers=JSON, json={"receipt_id": "some-id"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"]     == "Valid"
        assert body["confidence"] == "92%"

    @patch("app.validate_receipt", new_callable=AsyncMock, return_value=None)
    def test_not_found(self, _mock, client):
        resp = client.post("/validate", headers=JSON, json={"receipt_id": "ghost"})
        assert resp.status_code == 404

    def test_missing_receipt_id(self, client):
        resp = client.post("/validate", headers=JSON, json={})
        assert resp.status_code == 400

    def test_no_api_key(self, client):
        resp = client.post("/validate",
                           headers={"Content-Type": "application/json"},
                           json={"receipt_id": "x"})
        assert resp.status_code == 401


# ─── Generic error handling ───────────────────────────────────────────────────

class TestErrorHandlers:

    def test_404_unknown_route(self, client):
        resp = client.get("/does-not-exist")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_405_wrong_method(self, client):
        resp = client.get("/upload-receipt")   # GET instead of POST
        assert resp.status_code == 405
        assert "error" in resp.json()


# ─── Swagger UI ───────────────────────────────────────────────────────────────

class TestSwaggerDocs:

    def test_docs_available(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_schema_available(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert "paths" in resp.json()


# ─── Monitoring — /metrics ─────────────────────────────────────────────────────

class TestMetrics:

    def test_metrics_returns_200(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_no_auth_required(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type(self, client):
        resp = client.get("/metrics")
        assert "text/plain" in resp.headers["content-type"]

    def test_metrics_records_request_count(self, client):
        client.get("/health")
        resp = client.get("/metrics")
        body = resp.text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body


# ─── Background task on upload ────────────────────────────────────────────────

class TestBackgroundTask:

    @patch("app.save_receipt", new_callable=AsyncMock, return_value="receipt-uuid-002")
    @patch("app._post_upload_housekeeping")
    def test_background_task_called_on_upload(self, mock_housekeeping, _mock_save, client):
        files = {"file": ("bill.jpg", io.BytesIO(b"fake-image-data"), "image/jpeg")}
        resp = client.post("/upload-receipt", headers=AUTH, files=files)
        assert resp.status_code == 201

        # TestClient runs background tasks synchronously before returning,
        # so no sleep/wait is needed here (unlike Flask's daemon thread).
        mock_housekeeping.assert_called_once_with("receipt-uuid-002", "bill.jpg")


# ─── Rate limiting ────────────────────────────────────────────────────────────

class TestRateLimiting:
    """
    RATE_LIMIT_ENABLED=false is set at the top of this file, so these tests
    confirm the limiter is wired up WITHOUT it interfering with the rest of
    the suite. To test actual 429 behaviour, run with RATE_LIMIT_ENABLED=true
    and RATE_LIMIT_PER_MINUTE=1, then make 2 requests in a row.
    """

    def test_requests_succeed_when_disabled(self, client):
        # With limiting disabled, many rapid requests should all succeed.
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200


# ─── JWT authentication ────────────────────────────────────────────────────────

class TestJWTAuth:

    def test_token_issued_with_valid_api_key(self, client):
        resp = client.post("/token", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 3600  # default JWT_EXPIRY_MINUTES=60

    def test_token_rejected_without_api_key(self, client):
        resp = client.post("/token")
        assert resp.status_code == 401

    def test_token_rejected_with_wrong_api_key(self, client):
        resp = client.post("/token", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    @patch("app.extract_receipt", new_callable=AsyncMock, return_value=_EXTRACT_RESULT)
    def test_jwt_grants_access_to_protected_route(self, _mock, client):
        # Get a token, then use it instead of X-API-Key
        token = client.post("/token", headers=AUTH).json()["access_token"]

        resp = client.post(
            "/extract",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"receipt_id": "some-id"},
        )
        assert resp.status_code == 200
        assert resp.json()["merchant"] == "ABC Store"

    def test_invalid_jwt_rejected(self, client):
        resp = client.post(
            "/extract",
            headers={"Authorization": "Bearer not-a-real-token", "Content-Type": "application/json"},
            json={"receipt_id": "some-id"},
        )
        assert resp.status_code == 401

    def test_expired_jwt_rejected(self, client):
        import jwt as pyjwt

        expired_payload = {
            "sub": "api-client",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        expired_token = pyjwt.encode(expired_payload, "change-this-jwt-secret", algorithm="HS256")

        resp = client.post(
            "/extract",
            headers={"Authorization": f"Bearer {expired_token}", "Content-Type": "application/json"},
            json={"receipt_id": "some-id"},
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["error"].lower()

    def test_no_auth_still_rejected(self, client):
        resp = client.post(
            "/extract",
            headers={"Content-Type": "application/json"},
            json={"receipt_id": "some-id"},
        )
        assert resp.status_code == 401