"""
schema/receipt_request.py — Lightweight request body schemas.

Flask doesn't enforce schemas at the framework level (unlike FastAPI + Pydantic),
so these dataclasses serve as:
  • Clear documentation of expected request shapes
  • Optional manual validation helpers (from_dict raises ValueError on bad input)

Usage in a route (optional pattern):
    from schema.receipt_request import ExtractRequest
    try:
        req = ExtractRequest.from_dict(request.get_json() or {})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractRequest:
    """Request body for POST /extract."""
    receipt_id: str

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractRequest":
        receipt_id = (data.get("receipt_id") or "").strip()
        if not receipt_id:
            raise ValueError("'receipt_id' is required and must be a non-empty string")
        return cls(receipt_id=receipt_id)


@dataclass
class ValidateRequest:
    """Request body for POST /validate."""
    receipt_id: str

    @classmethod
    def from_dict(cls, data: dict) -> "ValidateRequest":
        receipt_id = (data.get("receipt_id") or "").strip()
        if not receipt_id:
            raise ValueError("'receipt_id' is required and must be a non-empty string")
        return cls(receipt_id=receipt_id)