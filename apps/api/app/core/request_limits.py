"""Request-body size limiting middleware and upload validation helpers.

- ``RequestSizeLimitMiddleware``: rejects requests whose ``Content-Length``
  header exceeds ``settings.request_max_body_mb``. Cheap check, runs before
  FastAPI reads the body.
- ``validate_upload``: per-endpoint helper that enforces max size,
  allowed extensions, and MIME-type magic-number validation. Raises
  ``PayloadTooLargeError`` / ``UnsupportedMediaTypeError`` from
  ``app.core.exceptions``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable

import magic
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError, UnsupportedMediaTypeError

logger = logging.getLogger(__name__)

UploadKind = str  # "audio" | "video" | "document" | "image"


# ─── Extension → MIME prefix mapping ────────────────────────

_EXTENSION_MIME_MAP: dict[str, list[str]] = {
    # Audio
    ".wav": ["audio/"],
    ".mp3": ["audio/"],
    ".m4a": ["audio/", "video/mp4"],  # m4a is technically MPEG-4 container
    ".ogg": ["audio/", "video/ogg"],
    ".flac": ["audio/"],
    ".webm": ["audio/", "video/webm"],
    # Video
    ".mp4": ["video/", "audio/mp4"],
    ".mov": ["video/"],
    ".avi": ["video/"],
    ".mkv": ["video/"],
    # Images
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".png": ["image/png"],
    ".webp": ["image/webp"],
    # Documents
    ".pdf": ["application/pdf"],
    ".docx": ["application/vnd.openxmlformats", "application/zip"],
    ".txt": ["text/"],
    ".csv": ["text/", "application/csv"],
    ".md": ["text/"],
}


# ─── Middleware ──────────────────────────────────────────────


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized requests early based on Content-Length.

    This is a first line of defense. The per-endpoint ``validate_upload``
    helper catches the case where Content-Length isn't set (e.g. chunked
    upload) by checking the actual bytes read.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        max_bytes = settings.request_max_body_mb * 1024 * 1024
        length_header = request.headers.get("content-length")
        if length_header:
            try:
                length = int(length_header)
            except ValueError:
                length = 0
            if length > max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "PAYLOAD_TOO_LARGE",
                            "message": (
                                f"Request body exceeds the {settings.request_max_body_mb} MB limit."
                            ),
                            "details": {
                                "content_length": length,
                                "max_bytes": max_bytes,
                            },
                        }
                    },
                )
        return await call_next(request)


# ─── Upload validation helpers ───────────────────────────────


def _category_limits(kind: UploadKind) -> tuple[int, list[str]]:
    """Return (max_bytes, allowed_extensions) for a category."""
    if kind == "audio":
        return (
            settings.upload_max_audio_mb * 1024 * 1024,
            settings.upload_audio_extensions,
        )
    if kind == "video":
        return (
            settings.upload_max_video_mb * 1024 * 1024,
            settings.upload_video_extensions,
        )
    if kind == "document":
        return (
            settings.upload_max_document_mb * 1024 * 1024,
            settings.upload_document_extensions,
        )
    if kind == "image":
        return (
            settings.upload_max_image_mb * 1024 * 1024,
            settings.upload_image_extensions,
        )
    raise ValueError(f"Unknown upload kind: {kind}")


def _validate_mime(ext: str, data: bytes, filename: str | None) -> None:
    """Check that the file's magic bytes match the claimed extension.

    Raises ``UnsupportedMediaTypeError`` when the detected MIME type
    does not match the allowed MIME prefixes for the given extension.
    """
    allowed_prefixes = _EXTENSION_MIME_MAP.get(ext)
    if allowed_prefixes is None:
        # Extension not in our map — skip magic check (extension filter
        # already ensures only whitelisted extensions reach here).
        return

    detected = magic.from_buffer(data[:8192], mime=True)
    if not any(detected.startswith(prefix) for prefix in allowed_prefixes):
        logger.warning(
            "MIME mismatch: filename=%s ext=%s detected=%s",
            filename,
            ext,
            detected,
        )
        raise UnsupportedMediaTypeError(
            f"File content does not match its extension '{ext}'. "
            f"Detected type: {detected}",
            details={
                "filename": filename,
                "extension": ext,
                "detected_mime": detected,
            },
        )


def validate_upload(
    *,
    filename: str | None,
    data: bytes,
    kind: UploadKind,
) -> None:
    """Validate an uploaded file's extension, MIME type, and byte size.

    Raises ``UnsupportedMediaTypeError`` or ``PayloadTooLargeError`` on
    failure. Use from router handlers after ``await file.read()``::

        data = await file.read()
        validate_upload(filename=file.filename, data=data, kind="audio")
    """
    max_bytes, allowed = _category_limits(kind)

    # Extension check
    ext = Path(filename or "").suffix.lower()
    if not ext or ext not in allowed:
        raise UnsupportedMediaTypeError(
            f"Unsupported {kind} format '{ext or '?'}'. "
            f"Allowed: {', '.join(sorted(allowed))}",
            details={"filename": filename, "allowed_extensions": sorted(allowed)},
        )

    # Magic-number MIME validation
    _validate_mime(ext, data, filename)

    # Size check
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"{kind.capitalize()} file exceeds the {max_bytes // (1024 * 1024)} MB limit.",
            details={"size": len(data), "max_bytes": max_bytes, "kind": kind},
        )


__all__ = ["RequestSizeLimitMiddleware", "validate_upload"]
