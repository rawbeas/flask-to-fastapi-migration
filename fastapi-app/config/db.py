"""
config/db.py — MongoDB Atlas connection setup using Motor (async).

Exports
-------
  client              — AsyncIOMotorClient instance
  db                  — the database (MONGODB_DB_NAME)
  get_bucket()        — returns AsyncIOMotorGridFSBucket (lazy, see note below)
  metadata_collection — Motor collection for receipt metadata documents
  check_connection()  — async helper, pings Atlas (called from app.py lifespan)

Notes
-----
  • Same MONGODB_URI as the Flask app — both services point at the same
    Atlas cluster, just through their own .env files.
  • ❌ Do NOT install pymongo[srv] — Motor already bundles pymongo internally.
  • ✅ pip install motor python-dotenv  (that's it)
  • Creating AsyncIOMotorClient does NOT connect immediately (it's lazy) —
    the actual connection + ping happens in app.py's lifespan on startup.
  • AsyncIOMotorGridFSBucket grabs the current event loop in its constructor.
    On Python 3.14, asyncio no longer auto-creates a loop, so constructing
    it at MODULE IMPORT TIME (before uvicorn's loop exists) raises:
        RuntimeError: There is no current event loop in thread 'MainThread'
    Fix: get_bucket() builds it lazily on first call FROM an async function
    (i.e. once uvicorn's event loop is already running).
"""

import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

load_dotenv()

# ── Read environment variables ────────────────────────────────────────────────
MONGODB_URI              = os.getenv("MONGODB_URI")
MONGODB_DB_NAME          = os.getenv("MONGODB_DB_NAME",     "receipt_verification_db")
GRIDFS_BUCKET_NAME       = os.getenv("GRIDFS_BUCKET_NAME",  "receipts")
METADATA_COLLECTION_NAME = os.getenv("METADATA_COLLECTION", "receipt_metadata")

if not MONGODB_URI:
    raise EnvironmentError(
        "\n"
        "  MONGODB_URI is not set!\n"
        "  Steps to fix:\n"
        "    1. Copy  .env.example  →  .env\n"
        "    2. Paste the SAME Atlas connection string used for the Flask app\n"
        "       as  MONGODB_URI=mongodb+srv://...\n"
        "    3. Restart the app\n"
    )

# ── Create Motor client, db, metadata collection ─────────────────────────────
# AsyncIOMotorClient() does not block / connect right away — it's lazy, and
# (unlike GridFSBucket) does NOT touch the event loop at construction time,
# so this is safe at module import time.
client = AsyncIOMotorClient(MONGODB_URI)
db                  = client[MONGODB_DB_NAME]
metadata_collection = db[METADATA_COLLECTION_NAME]

_bucket: AsyncIOMotorGridFSBucket | None = None


def get_bucket() -> AsyncIOMotorGridFSBucket:
    """
    Return the GridFS bucket, creating it on first call.

    Must be called from within an async function (i.e. while uvicorn's
    event loop is running) — never at module import time. services/storage.py
    calls this inside its async functions, so this is satisfied automatically.
    """
    global _bucket
    if _bucket is None:
        _bucket = AsyncIOMotorGridFSBucket(db, bucket_name=GRIDFS_BUCKET_NAME)
    return _bucket


async def check_connection() -> None:
    """
    Ping Atlas to verify the connection actually works.
    Called once from app.py's lifespan() on startup — fails fast with a
    clear error instead of every request silently timing out.
    """
    await client.admin.command("ping")