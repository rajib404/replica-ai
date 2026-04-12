import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.voice import VerificationResult
from app.routers.voice import _get_voice_manager


# ─── Helpers ─────────────────────────────────────────────


OWNER_ID = "owner-voice-123"


def _owner_token(owner_id: str = OWNER_ID) -> str:
    return create_access_token(subject=owner_id, role="owner")


def _auth_header(owner_id: str = OWNER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_owner_token(owner_id)}"}


def _create_owner(client: TestClient) -> str:
    resp = client.post(
        "/api/auth/setup",
        json={
            "name": "Voice Test Owner",
            "email": "voicetest@example.com",
            "preferred_language": "en",
            "secret_word": "testsecret",
        },
    )
    assert resp.status_code == 201
    return resp.json()["owner_id"]


def _mock_voice_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.enroll_voice = AsyncMock(return_value={
        "status": "enrolled",
        "samples_received": 3,
        "samples_required": 3,
        "message": "Voice profile enrolled successfully with 3 samples.",
    })
    manager.verify_voice = AsyncMock(return_value=VerificationResult(
        verified=True,
        similarity_score=0.89,
        threshold=0.75,
    ))
    manager.get_enrollment_status = AsyncMock(return_value={
        "enrolled": True,
        "samples_stored": 3,
        "samples_required": 3,
    })
    return manager


def _fake_audio_file(name: str = "sample.wav", size: int = 1024) -> tuple[str, io.BytesIO, str]:
    """Create a fake audio file tuple for multipart uploads."""
    return (name, io.BytesIO(b"\x00" * size), "audio/wav")


def _override_manager(manager: AsyncMock) -> None:
    from app.main import app
    app.dependency_overrides[_get_voice_manager] = lambda: manager


def _clear_overrides() -> None:
    from app.main import app
    app.dependency_overrides.pop(_get_voice_manager, None)


# ─── POST /api/verify/voice/enroll ──────────────────────


def test_voice_enroll_success(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    _override_manager(manager)

    files = [
        ("samples", ("sample1.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
        ("samples", ("sample2.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
        ("samples", ("sample3.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
    ]
    resp = client.post(
        "/api/verify/voice/enroll",
        files=files,
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "enrolled"
    assert data["samples_received"] == 3
    manager.enroll_voice.assert_called_once()

    _clear_overrides()


def test_voice_enroll_requires_auth(client: TestClient) -> None:
    files = [
        ("samples", ("sample1.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
        ("samples", ("sample2.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
        ("samples", ("sample3.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
    ]
    resp = client.post("/api/verify/voice/enroll", files=files)
    assert resp.status_code == 403 or resp.status_code == 401


def test_voice_enroll_too_few_samples(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    _override_manager(manager)

    files = [
        ("samples", ("sample1.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")),
    ]
    resp = client.post(
        "/api/verify/voice/enroll",
        files=files,
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 422

    _clear_overrides()


def test_voice_enroll_bad_format(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    _override_manager(manager)

    files = [
        ("samples", ("sample1.exe", io.BytesIO(b"\x00" * 1024), "application/octet-stream")),
        ("samples", ("sample2.exe", io.BytesIO(b"\x00" * 1024), "application/octet-stream")),
        ("samples", ("sample3.exe", io.BytesIO(b"\x00" * 1024), "application/octet-stream")),
    ]
    resp = client.post(
        "/api/verify/voice/enroll",
        files=files,
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 422

    _clear_overrides()


# ─── POST /api/verify/voice/check ───────────────────────


def test_voice_check_success(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    _override_manager(manager)

    resp = client.post(
        "/api/verify/voice/check",
        files={"sample": ("test.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is True
    assert data["similarity_score"] == 0.89
    assert data["threshold"] == 0.75
    manager.verify_voice.assert_called_once()

    _clear_overrides()


def test_voice_check_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/verify/voice/check",
        files={"sample": ("test.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")},
    )
    assert resp.status_code == 403 or resp.status_code == 401


def test_voice_check_no_profile(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    manager.verify_voice = AsyncMock(side_effect=ValueError("No voice profile enrolled for this owner"))
    _override_manager(manager)

    resp = client.post(
        "/api/verify/voice/check",
        files={"sample": ("test.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 400
    assert "No voice profile" in resp.json()["detail"]

    _clear_overrides()


def test_voice_check_failed_verification(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    manager.verify_voice = AsyncMock(return_value=VerificationResult(
        verified=False,
        similarity_score=0.52,
        threshold=0.75,
    ))
    _override_manager(manager)

    resp = client.post(
        "/api/verify/voice/check",
        files={"sample": ("test.wav", io.BytesIO(b"\x00" * 1024), "audio/wav")},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is False
    assert data["similarity_score"] == 0.52
    assert "failed" in data["message"].lower()

    _clear_overrides()


# ─── GET /api/verify/voice/status ────────────────────────


def test_voice_status_enrolled(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    _override_manager(manager)

    resp = client.get("/api/verify/voice/status", headers=_auth_header(owner_id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["enrolled"] is True
    assert data["samples_stored"] == 3

    _clear_overrides()


def test_voice_status_not_enrolled(client: TestClient) -> None:
    owner_id = _create_owner(client)
    manager = _mock_voice_manager()
    manager.get_enrollment_status = AsyncMock(return_value={
        "enrolled": False,
        "samples_stored": 0,
        "samples_required": 3,
    })
    _override_manager(manager)

    resp = client.get("/api/verify/voice/status", headers=_auth_header(owner_id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["enrolled"] is False
    assert data["samples_stored"] == 0

    _clear_overrides()


def test_voice_status_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/verify/voice/status")
    assert resp.status_code == 403 or resp.status_code == 401
