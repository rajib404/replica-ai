"""Unit tests for request size limits and upload validation."""

from __future__ import annotations

import pytest

from app.core.exceptions import PayloadTooLargeError, UnsupportedMediaTypeError
from app.core.request_limits import _category_limits, validate_upload


class TestCategoryLimits:
    def test_audio_limits(self) -> None:
        max_bytes, allowed = _category_limits("audio")
        assert max_bytes == 50 * 1024 * 1024
        assert ".mp3" in allowed
        assert ".wav" in allowed

    def test_video_limits(self) -> None:
        max_bytes, allowed = _category_limits("video")
        assert max_bytes == 500 * 1024 * 1024
        assert ".mp4" in allowed

    def test_document_limits(self) -> None:
        max_bytes, allowed = _category_limits("document")
        assert max_bytes == 25 * 1024 * 1024
        assert ".pdf" in allowed
        assert ".txt" in allowed

    def test_image_limits(self) -> None:
        max_bytes, allowed = _category_limits("image")
        assert max_bytes == 10 * 1024 * 1024
        assert ".jpg" in allowed
        assert ".png" in allowed

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown upload kind"):
            _category_limits("hologram")  # type: ignore[arg-type]


class TestValidateUpload:
    def test_accepts_valid_audio(self) -> None:
        validate_upload(filename="clip.mp3", data=b"x" * 1024, kind="audio")

    def test_accepts_valid_uppercase_extension(self) -> None:
        """Extension comparison is case-insensitive."""
        validate_upload(filename="VIDEO.MP4", data=b"x" * 1024, kind="video")

    def test_rejects_wrong_extension(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError) as exc_info:
            validate_upload(filename="doc.exe", data=b"x", kind="document")
        assert exc_info.value.status_code == 415
        assert "allowed_extensions" in exc_info.value.details

    def test_rejects_missing_extension(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError):
            validate_upload(filename="noextension", data=b"x", kind="audio")

    def test_rejects_missing_filename(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError):
            validate_upload(filename=None, data=b"x", kind="audio")

    def test_rejects_audio_over_limit(self) -> None:
        oversized = b"x" * (51 * 1024 * 1024)
        with pytest.raises(PayloadTooLargeError) as exc_info:
            validate_upload(filename="big.mp3", data=oversized, kind="audio")
        assert exc_info.value.status_code == 413
        assert exc_info.value.details["kind"] == "audio"
        assert exc_info.value.details["size"] == len(oversized)

    def test_accepts_exactly_at_limit(self) -> None:
        """Boundary case: file exactly at the limit is accepted."""
        exactly_25mb = b"x" * (25 * 1024 * 1024)
        validate_upload(filename="doc.pdf", data=exactly_25mb, kind="document")

    def test_one_byte_over_rejected(self) -> None:
        one_over = b"x" * (25 * 1024 * 1024 + 1)
        with pytest.raises(PayloadTooLargeError):
            validate_upload(filename="doc.pdf", data=one_over, kind="document")

    def test_error_details_include_filename(self) -> None:
        with pytest.raises(UnsupportedMediaTypeError) as exc_info:
            validate_upload(filename="file.xyz", data=b"x", kind="audio")
        assert exc_info.value.details["filename"] == "file.xyz"

    def test_image_kind(self) -> None:
        validate_upload(filename="avatar.png", data=b"x" * 100, kind="image")
        with pytest.raises(PayloadTooLargeError):
            validate_upload(
                filename="huge.jpg", data=b"x" * (11 * 1024 * 1024), kind="image"
            )
