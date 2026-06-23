"""
services/storage.py — Persist and retrieve receipts using MongoDB.

GridFS  → stores raw file bytes (images / PDFs)
Metadata collection → stores structured info per receipt

Public API
----------
  save_receipt(file_bytes, filename, content_type) -> receipt_id
  get_receipt_bytes(receipt_id)                    -> bytes | None
  get_receipt_metadata(receipt_id)                 -> dict | None
  update_receipt_metadata(receipt_id, fields)      -> None
"""

import logging
import uuid
from datetime import datetime, timezone

from config.db import bucket, metadata_collection

logger = logging.getLogger(__name__)


# ─── Write ────────────────────────────────────────────────────────────────────

def save_receipt(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Store a receipt file in GridFS and write a metadata document.

    Parameters
    ----------
    file_bytes   : raw bytes of the uploaded file
    filename     : original filename from the upload (e.g. "receipt.jpg")
    content_type : MIME type (e.g. "image/jpeg")

    Returns
    -------
    receipt_id : UUID string that clients use in /extract and /validate calls
    """
    receipt_id = str(uuid.uuid4())
    content_type = content_type or "application/octet-stream"

    # 1 ── Store file bytes in GridFS ─────────────────────────────────────────
    #      bucket.put() returns an ObjectId we keep in the metadata document
    #      so we can retrieve the file later via bucket.get(gridfs_id).
    gridfs_id = bucket.put(
        file_bytes,
        filename=filename,
        content_type=content_type,
        receipt_id=receipt_id,   # custom field — makes querying GridFS easier
    )
    logger.info("GridFS write OK — gridfs_id=%s  receipt_id=%s", gridfs_id, receipt_id)

    # 2 ── Write metadata document ─────────────────────────────────────────────
    doc = {
        "receipt_id":   receipt_id,
        "filename":     filename,
        "content_type": content_type,
        "gridfs_id":    gridfs_id,           # ObjectId that links to the GridFS file
        "file_size":    len(file_bytes),
        "uploaded_at":  datetime.now(timezone.utc),
        "extracted":    False,
        "validated":    False,
    }
    metadata_collection.insert_one(doc)
    logger.info("Metadata saved — receipt_id=%s", receipt_id)

    return receipt_id


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_receipt_bytes(receipt_id: str) -> bytes | None:
    """
    Retrieve raw file bytes from GridFS for a given receipt_id.
    Returns None if the receipt_id does not exist.
    """
    doc = metadata_collection.find_one({"receipt_id": receipt_id})
    if not doc:
        logger.warning("get_receipt_bytes — receipt_id=%s not found", receipt_id)
        return None

    gridfs_file = bucket.get(doc["gridfs_id"])
    return gridfs_file.read()


def get_receipt_metadata(receipt_id: str) -> dict | None:
    """
    Return the metadata document for a receipt_id.
    ObjectId and datetime fields are serialised to strings so the caller
    can safely pass the result to jsonify() if needed.
    Returns None if the receipt_id does not exist.
    """
    doc = metadata_collection.find_one({"receipt_id": receipt_id})
    if not doc:
        return None

    # Convert non-JSON-serialisable types
    doc["_id"]      = str(doc["_id"])
    doc["gridfs_id"] = str(doc["gridfs_id"])
    if hasattr(doc.get("uploaded_at"), "isoformat"):
        doc["uploaded_at"] = doc["uploaded_at"].isoformat()

    return doc


# ─── Update ───────────────────────────────────────────────────────────────────

def update_receipt_metadata(receipt_id: str, update_fields: dict) -> None:
    """
    Merge *update_fields* into the existing metadata document for receipt_id.
    Used by receipt_service to cache extracted / validated results.
    """
    metadata_collection.update_one(
        {"receipt_id": receipt_id},
        {"$set": update_fields},
    )
    logger.debug("Metadata updated — receipt_id=%s  fields=%s", receipt_id, list(update_fields))