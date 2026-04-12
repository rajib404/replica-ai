"""Unit tests for the custom exception hierarchy."""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    AppError,
    AuthError,
    ConflictError,
    DatabaseError,
    ForbiddenError,
    InsufficientFundsError,
    ModelUnavailableError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    StorageError,
    SyncConflictError,
    UnsupportedMediaTypeError,
    UpstreamError,
    ValidationError,
)


class TestAppErrorBase:
    def test_default_message_used_when_none_provided(self) -> None:
        err = AppError()
        assert err.message == AppError.default_message
        assert err.details == {}
        assert err.code == "APP_ERROR"
        assert err.status_code == 500

    def test_custom_message_overrides_default(self) -> None:
        err = AppError("specific failure")
        assert err.message == "specific failure"

    def test_details_preserved(self) -> None:
        err = AppError("boom", details={"field": "email", "reason": "invalid"})
        assert err.details == {"field": "email", "reason": "invalid"}

    def test_to_dict_shape(self) -> None:
        err = AuthError("bad token", details={"token_type": "access"})
        envelope = err.to_dict()
        assert envelope == {
            "error": {
                "code": "AUTH_FAILED",
                "message": "bad token",
                "details": {"token_type": "access"},
            }
        }

    def test_is_exception(self) -> None:
        with pytest.raises(AppError) as exc_info:
            raise AppError("thrown")
        assert str(exc_info.value) == "thrown"


@pytest.mark.parametrize(
    ("cls", "code", "status", "log_level"),
    [
        (AuthError, "AUTH_FAILED", 401, "warning"),
        (ForbiddenError, "FORBIDDEN", 403, "warning"),
        (NotFoundError, "NOT_FOUND", 404, "warning"),
        (ValidationError, "VALIDATION_ERROR", 400, "warning"),
        (ConflictError, "CONFLICT", 409, "warning"),
        (RateLimitError, "RATE_LIMIT_EXCEEDED", 429, "warning"),
        (PayloadTooLargeError, "PAYLOAD_TOO_LARGE", 413, "warning"),
        (UnsupportedMediaTypeError, "UNSUPPORTED_MEDIA_TYPE", 415, "warning"),
        (InsufficientFundsError, "INSUFFICIENT_FUNDS", 402, "warning"),
        (SyncConflictError, "SYNC_CONFLICT", 409, "warning"),
        (ModelUnavailableError, "MODEL_UNAVAILABLE", 503, "error"),
        (UpstreamError, "UPSTREAM_ERROR", 502, "error"),
        (StorageError, "STORAGE_ERROR", 500, "error"),
        (DatabaseError, "DATABASE_ERROR", 500, "error"),
    ],
)
def test_subclass_metadata(
    cls: type[AppError], code: str, status: int, log_level: str
) -> None:
    """Every subclass exposes the documented code/status/log level."""
    instance = cls()
    assert instance.code == code
    assert instance.status_code == status
    assert instance.log_level == log_level
    assert instance.message  # default message is non-empty


def test_all_subclasses_derive_from_app_error() -> None:
    for cls in (
        AuthError,
        ForbiddenError,
        NotFoundError,
        ValidationError,
        ConflictError,
        RateLimitError,
        PayloadTooLargeError,
        UnsupportedMediaTypeError,
        InsufficientFundsError,
        SyncConflictError,
        ModelUnavailableError,
        UpstreamError,
        StorageError,
        DatabaseError,
    ):
        assert issubclass(cls, AppError)
        assert issubclass(cls, Exception)


def test_to_dict_includes_empty_details_key() -> None:
    """Clients rely on ``details`` always being present (even if empty)."""
    err = ValidationError("bad shape")
    assert "details" in err.to_dict()["error"]
    assert err.to_dict()["error"]["details"] == {}
