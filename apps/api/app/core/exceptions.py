"""Custom exception hierarchy for the Replica AI API.

All application errors inherit from ``AppError``. The global exception
handler (``app.core.exception_handlers``) translates them into a consistent
JSON envelope:

    {
        "error": {
            "code": "AUTH_FAILED",
            "message": "...",
            "details": {...}
        }
    }

Guidelines
----------
- Raise ``AppError`` subclasses from routers and services instead of
  ``HTTPException``.
- Use ``details`` to carry structured context useful to the client.
- ``AppError.log_level`` controls how the global handler logs the error
  (``warning`` for expected client errors, ``error`` for server faults).
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application-level errors.

    Subclasses should override ``code`` and ``status_code`` and may set
    ``log_level`` to ``"error"`` for unexpected conditions.
    """

    code: str = "APP_ERROR"
    status_code: int = 500
    log_level: str = "warning"  # "warning" | "error"
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details: dict[str, Any] = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# ─── 4xx — client errors ─────────────────────────────────────────


class AuthError(AppError):
    """Authentication failed: missing, invalid or expired credentials."""

    code = "AUTH_FAILED"
    status_code = 401
    default_message = "Authentication failed."


class ForbiddenError(AppError):
    """Caller is authenticated but not permitted to perform the action."""

    code = "FORBIDDEN"
    status_code = 403
    default_message = "You don't have permission to do that."


class NotFoundError(AppError):
    """Requested resource doesn't exist."""

    code = "NOT_FOUND"
    status_code = 404
    default_message = "Resource not found."


class ValidationError(AppError):
    """Request payload failed domain validation (not schema validation)."""

    code = "VALIDATION_ERROR"
    status_code = 400
    default_message = "The request is invalid."


class ConflictError(AppError):
    """Resource already exists or conflicts with current state."""

    code = "CONFLICT"
    status_code = 409
    default_message = "The request conflicts with the current state."


class RateLimitError(AppError):
    """Too many requests from this caller."""

    code = "RATE_LIMIT_EXCEEDED"
    status_code = 429
    default_message = "Rate limit exceeded. Please slow down and try again."


class PayloadTooLargeError(AppError):
    """Upload exceeds the configured size limit."""

    code = "PAYLOAD_TOO_LARGE"
    status_code = 413
    default_message = "Request payload is too large."


class UnsupportedMediaTypeError(AppError):
    """File extension or MIME type is not accepted by this endpoint."""

    code = "UNSUPPORTED_MEDIA_TYPE"
    status_code = 415
    default_message = "This file type is not supported."


# ─── 4xx — domain-specific ───────────────────────────────────────


class InsufficientFundsError(AppError):
    """External LLM / billing budget exhausted."""

    code = "INSUFFICIENT_FUNDS"
    status_code = 402
    default_message = "Insufficient funds or monthly budget exhausted."


class SyncConflictError(AppError):
    """Replica sync detected divergent state between instances."""

    code = "SYNC_CONFLICT"
    status_code = 409
    default_message = "Sync conflict detected between instances."


# ─── 5xx — server / upstream errors ──────────────────────────────


class ModelUnavailableError(AppError):
    """Local LLM (Ollama) or external LLM is unreachable.

    503 is the right code for this: the service exists but can't serve
    the request right now. Clients can retry safely.
    """

    code = "MODEL_UNAVAILABLE"
    status_code = 503
    log_level = "error"
    default_message = (
        "The AI model is temporarily unavailable. Please try again in a minute."
    )


class UpstreamError(AppError):
    """A downstream service (ai service, external API) returned an error."""

    code = "UPSTREAM_ERROR"
    status_code = 502
    log_level = "error"
    default_message = "An upstream service returned an error."


class StorageError(AppError):
    """Filesystem or object-store operation failed."""

    code = "STORAGE_ERROR"
    status_code = 500
    log_level = "error"
    default_message = "Storage operation failed."


class DatabaseError(AppError):
    """Unrecoverable database error after retries."""

    code = "DATABASE_ERROR"
    status_code = 500
    log_level = "error"
    default_message = "Database operation failed."


__all__ = [
    "AppError",
    "AuthError",
    "ForbiddenError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "RateLimitError",
    "PayloadTooLargeError",
    "UnsupportedMediaTypeError",
    "InsufficientFundsError",
    "SyncConflictError",
    "ModelUnavailableError",
    "UpstreamError",
    "StorageError",
    "DatabaseError",
]
