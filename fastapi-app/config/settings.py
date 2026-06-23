"""
config/settings.py — Application settings loaded from the .env file.

Same pattern as the Flask app's config/settings.py — kept for parity
between the two services.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── Auth ──────────────────────────────────────────────────────────────────
    API_KEY: str = os.getenv("API_KEY", "change-me")

    # ── MongoDB Atlas ─────────────────────────────────────────────────────────
    MONGODB_URI: str | None  = os.getenv("MONGODB_URI")
    MONGODB_DB_NAME: str     = os.getenv("MONGODB_DB_NAME",     "receipt_verification_db")
    GRIDFS_BUCKET_NAME: str  = os.getenv("GRIDFS_BUCKET_NAME",  "receipts")
    METADATA_COLLECTION: str = os.getenv("METADATA_COLLECTION", "receipt_metadata")

    # ── Upload limits ─────────────────────────────────────────────────────────
    MAX_FILE_SIZE_MB: int = 5

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Set RATE_LIMIT_ENABLED=false in .env to disable entirely (e.g. during tests).
    # Default storage (slowapi/limits in-memory) is per-process — fine for a
    # single uvicorn worker / dev. With --workers > 1 in production, point
    # RATELIMIT_STORAGE_URI at a shared Redis instance so limits apply across
    # all worker processes.
    RATE_LIMIT_ENABLED: bool   = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    RATELIMIT_STORAGE_URI: str = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # ── JWT authentication ────────────────────────────────────────────────────
    # Second auth method alongside X-API-Key. Get a token via POST /token
    # (using X-API-Key), then send it as  Authorization: Bearer <token>.
    # ⚠️ Change JWT_SECRET_KEY in .env for any real deployment — this default
    # is only for local dev.
    JWT_SECRET_KEY: str     = os.getenv("JWT_SECRET_KEY", "change-this-jwt-secret")
    JWT_ALGORITHM: str      = "HS256"
    JWT_EXPIRY_MINUTES: int = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))


settings = Settings()