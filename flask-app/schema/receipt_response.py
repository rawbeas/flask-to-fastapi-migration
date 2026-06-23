"""
schema/receipt_response.py — Response shape definitions.

These dataclasses document exactly what each endpoint returns.
to_dict() gives a plain dict ready for jsonify().

These also serve as the spec for the FastAPI migration — Pydantic models
will replace these dataclasses in the FastAPI version.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class UploadResponse:
    """Response from POST /upload-receipt."""
    receipt_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractResponse:
    """Response from POST /extract."""
    merchant: str
    date: str
    amount: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidateResponse:
    """Response from POST /validate."""
    status: str       # "Valid" | "Invalid" | "Uncertain"
    confidence: str   # e.g. "92%"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HealthResponse:
    """Response from GET /health."""
    status: str
    service: str

    def to_dict(self) -> dict:
        return asdict(self)