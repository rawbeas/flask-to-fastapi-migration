"""
schema/receipt_response.py — Pydantic response models.

Using response_model= on each route gives:
  • Automatic validation of what the route returns
  • Auto-generated example schemas in Swagger UI (/docs)
"""

from pydantic import BaseModel, ConfigDict


class UploadResponse(BaseModel):
    """Response from POST /upload-receipt."""
    receipt_id: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"receipt_id": "3b1f2c4e-..."}}
    )


class ExtractResponse(BaseModel):
    """Response from POST /extract."""
    merchant: str
    date: str
    amount: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"merchant": "ABC Store", "date": "2026-06-01", "amount": "500.00"}
        }
    )


class ValidateResponse(BaseModel):
    """Response from POST /validate."""
    status: str       # "Valid" | "Invalid" | "Uncertain"
    confidence: str   # e.g. "92%"

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "Valid", "confidence": "92%"}}
    )


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str
    service: str


class TokenResponse(BaseModel):
    """Response from POST /token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        }
    )


class ErrorResponse(BaseModel):
    """Shape of all error responses — matches the Flask version's {"error": "..."}."""
    error: str