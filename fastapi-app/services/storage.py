"""
services/storage.py — Persist and retrieve receipts using MongoDB (async).

GridFS  → stores raw file bytes (images / PDFs), via AsyncIOMotorGridFSBucket
Metadata collection → stores structured info per receipt

Public API (all async — must be awaited)
------------------------------------------
  await save_receipt(file_bytes, filename, content_type) -> receipt_id
  await get_receipt_bytes(receipt_id)                    -> bytes | None
  await get_receipt_metadata(receipt_id)                 -> dict | None
  await update_receipt_metadata(receipt_id, fields)      -> None
"""

import logging
import uuid
from datetime import datetime, timezone

from config.db import get_bucket, metadata_collection

logger = logging.getLogger(__name__)


# ─── Write ────────────────────────────────────────────────────────────────────

async def save_receipt(file_bytes: bytes, filename: str, content_type: str) -> str:
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
    #      upload_from_stream() is async and returns the ObjectId of the
    #      stored file — we keep this in the metadata document so we can
    #      retrieve the bytes later via bucket.open_download_stream(gridfs_id).
    bucket = get_bucket()
    gridfs_id = await bucket.upload_from_stream(
        filename,
        file_bytes,
        metadata={"content_type": content_type, "receipt_id": receipt_id},
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
    await metadata_collection.insert_one(doc)
    logger.info("Metadata saved — receipt_id=%s", receipt_id)

    return receipt_id


# ─── Read ─────────────────────────────────────────────────────────────────────

async def get_receipt_bytes(receipt_id: str) -> bytes | None:
    """
    Retrieve raw file bytes from GridFS for a given receipt_id.
    Returns None if the receipt_id does not exist.
    """
    doc = await metadata_collection.find_one({"receipt_id": receipt_id})
    if not doc:
        logger.warning("get_receipt_bytes — receipt_id=%s not found", receipt_id)
        return None

    bucket = get_bucket()
    stream = await bucket.open_download_stream(doc["gridfs_id"])
    return await stream.read()


async def get_receipt_metadata(receipt_id: str) -> dict | None:
    """
    Return the metadata document for a receipt_id.
    ObjectId and datetime fields are serialised to strings so the result
    is safe to return directly as a JSON response.
    Returns None if the receipt_id does not exist.
    """
    doc = await metadata_collection.find_one({"receipt_id": receipt_id})
    if not doc:
        return None

    # Convert non-JSON-serialisable types
    doc["_id"]       = str(doc["_id"])
    doc["gridfs_id"] = str(doc["gridfs_id"])
    if hasattr(doc.get("uploaded_at"), "isoformat"):
        doc["uploaded_at"] = doc["uploaded_at"].isoformat()

    return doc


# ─── Update ───────────────────────────────────────────────────────────────────

async def update_receipt_metadata(receipt_id: str, update_fields: dict) -> None:
    """
    Merge *update_fields* into the existing metadata document for receipt_id.
    Used by receipt_service to cache extracted / validated results.
    """
    await metadata_collection.update_one(
        {"receipt_id": receipt_id},
        {"$set": update_fields},
    )
    logger.debug("Metadata updated — receipt_id=%s  fields=%s", receipt_id, list(update_fields))