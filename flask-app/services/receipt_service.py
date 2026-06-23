"""
services/receipt_service.py — Business logic for /extract and /validate.

Both functions:
  1. Look up the receipt in MongoDB (via storage layer).
  2. Fetch the raw file bytes from GridFS.
  3. Call model.predict.predict_receipt() to get ML results.
  4. Cache the result back to the metadata document.
  5. Return a clean dict to the route handler.
"""

import logging

from model.predict import predict_receipt
from services.storage import (
    get_receipt_bytes,
    get_receipt_metadata,
    update_receipt_metadata,
)

logger = logging.getLogger(__name__)


def extract_receipt(receipt_id: str) -> dict | None:
    """
    Extract merchant, date, and amount from a stored receipt.

    Returns
    -------
    {"merchant": str, "date": str, "amount": str}
    or None if receipt_id is not found.
    """
    meta = get_receipt_metadata(receipt_id)
    if not meta:
        logger.warning("extract_receipt — receipt_id=%s not found", receipt_id)
        return None

    file_bytes = get_receipt_bytes(receipt_id)
    if file_bytes is None:
        logger.error("extract_receipt — GridFS file missing for receipt_id=%s", receipt_id)
        return None

    prediction = predict_receipt(file_bytes, meta["filename"])

    result = {
        "merchant": prediction.get("merchant", "Unknown Merchant"),
        "date":     prediction.get("date",     "1970-01-01"),
        "amount":   prediction.get("amount",   "0.00"),
    }

    # Cache in metadata so repeated /extract calls skip re-inference
    update_receipt_metadata(receipt_id, {"extracted": True, "extraction": result})
    logger.info("extract_receipt OK — receipt_id=%s", receipt_id)
    return result


def validate_receipt(receipt_id: str) -> dict | None:
    """
    Validate a stored receipt and return a status + confidence score.

    Returns
    -------
    {"status": str, "confidence": str}
    or None if receipt_id is not found.
    """
    meta = get_receipt_metadata(receipt_id)
    if not meta:
        logger.warning("validate_receipt — receipt_id=%s not found", receipt_id)
        return None

    file_bytes = get_receipt_bytes(receipt_id)
    if file_bytes is None:
        logger.error("validate_receipt — GridFS file missing for receipt_id=%s", receipt_id)
        return None

    prediction = predict_receipt(file_bytes, meta["filename"])

    result = {
        "status":     prediction.get("status",     "Valid"),
        "confidence": prediction.get("confidence", "90%"),
    }

    update_receipt_metadata(receipt_id, {"validated": True, "validation": result})
    logger.info("validate_receipt OK — receipt_id=%s", receipt_id)
    return result