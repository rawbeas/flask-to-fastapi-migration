"""
schema/receipt_request.py — Pydantic request models.

FastAPI validates the JSON body against these models automatically.
If validation fails (e.g. missing or empty receipt_id), FastAPI raises
RequestValidationError — which app.py converts into a 400 response with
{"error": "..."} to stay consistent with the Flask version.
"""

from pydantic import BaseModel, Field, field_validator


class ExtractRequest(BaseModel):
    """Request body for POST /extract."""
    receipt_id: str = Field(..., description="UUID returned by /upload-receipt")

    @field_validator("receipt_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("receipt_id must be a non-empty string")
        return v


class ValidateRequest(BaseModel):
    """Request body for POST /validate."""
    receipt_id: str = Field(..., description="UUID returned by /upload-receipt")

    @field_validator("receipt_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("receipt_id must be a non-empty string")
        return v