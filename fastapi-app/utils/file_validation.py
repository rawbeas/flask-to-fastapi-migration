"""
utils/file_validation.py — Validate uploaded receipt files before processing.

Rules (same as Flask version)
------------------------------
  Allowed extensions : jpg, jpeg, png, pdf
  Max file size      : 5 MB

Usage
-----
    from utils.file_validation import validate_file

    file_bytes = await file.read()          # read once
    error = validate_file(file.filename, file_bytes)
    if error:
        raise HTTPException(status_code=400, detail=error)
    # reuse file_bytes — no need to re-read
"""

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"jpg", "jpeg", "png", "pdf"})
MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB


def _get_extension(filename: str) -> str:
    """Return the lowercase extension without the leading dot, e.g. 'jpg'."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def validate_file(filename: str, file_bytes: bytes) -> str | None:
    """
    Validate an uploaded file against extension allowlist and max size limit.

    Parameters
    ----------
    filename   : original filename from the upload (e.g. "receipt.jpg")
    file_bytes : raw bytes already read from the UploadFile

    Returns
    -------
    str  — human-readable error message if validation fails
    None — if the file is acceptable
    """
    filename = filename or ""

    # ── 1. Extension check ────────────────────────────────────────────────────
    ext = _get_extension(filename)
    if not ext:
        return (
            "Could not determine file type. "
            f"Accepted types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if ext not in ALLOWED_EXTENSIONS:
        return (
            f"File type '.{ext}' is not allowed. "
            f"Accepted types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # ── 2. Size check ─────────────────────────────────────────────────────────
    size_bytes = len(file_bytes)

    if size_bytes == 0:
        return "Uploaded file is empty (0 bytes)."

    if size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = size_bytes / (1024 * 1024)
        return (
            f"File size {size_mb:.1f} MB exceeds the maximum allowed size of "
            f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    return None  # ← file is valid