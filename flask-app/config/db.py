"""
config/db.py — MongoDB Atlas connection setup.

Exports
-------
  client              — MongoClient instance
  db                  — the database (MONGODB_DB_NAME)
  bucket              — gridfs.GridFS instance for storing receipt files
  metadata_collection — pymongo Collection for receipt metadata documents

This module is imported by services/storage.py.
On first import it connects to Atlas and does a ping to verify the connection.
If MONGODB_URI is not set it raises EnvironmentError immediately so you get
a clear error message instead of a confusing AttributeError later.
"""

import os

import gridfs
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# load_dotenv is idempotent — safe to call here even though settings.py also calls it
load_dotenv()

# ── Read environment variables ────────────────────────────────────────────────
MONGODB_URI             = os.getenv("MONGODB_URI")
MONGODB_DB_NAME         = os.getenv("MONGODB_DB_NAME",    "receipt_verification_db")
GRIDFS_BUCKET_NAME      = os.getenv("GRIDFS_BUCKET_NAME", "receipts")
METADATA_COLLECTION_NAME = os.getenv("METADATA_COLLECTION","receipt_metadata")

if not MONGODB_URI:
    raise EnvironmentError(
        "\n"
        "  MONGODB_URI is not set!\n"
        "  Steps to fix:\n"
        "    1. Copy  .env.example  →  .env\n"
        "    2. Paste your Atlas connection string as  MONGODB_URI=mongodb+srv://...\n"
        "    3. Restart the app\n"
    )

# ── Connect to MongoDB Atlas ──────────────────────────────────────────────────
# serverSelectionTimeoutMS=5000 → fail fast with a clear error instead of hanging
try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    # ping verifies the connection actually works at startup
    client.admin.command("ping")
    print("✅  MongoDB Atlas — connected successfully")
except ConnectionFailure as exc:
    raise RuntimeError(
        f"❌  Could not connect to MongoDB Atlas.\n"
        f"    Check your MONGODB_URI and Atlas Network Access settings.\n"
        f"    Original error: {exc}"
    ) from exc

# ── Database, GridFS bucket, metadata collection ──────────────────────────────
db                  = client[MONGODB_DB_NAME]
bucket              = gridfs.GridFS(db, collection=GRIDFS_BUCKET_NAME)
metadata_collection = db[METADATA_COLLECTION_NAME]