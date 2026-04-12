"""Tests for the identity protection system."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.identity import (
    ChallengeLevel,
    ChallengeResponse,
    GuardCheckResult,
)
from app.routers.chat import _get_conversation_manager, _get_identity_guard, _get_ingestor, _get_rag_engine


# ─── Helpers ─────────────────────────────────────────────


OWNER_ID = "owner-guard-123"


def _owner_token(owner_id: str = OWNER_ID) -> str:
    return create_access_token(subject=owner_id, role="owner")


def _auth_header(owner_id: str = OWNER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_owner_token(owner_id)}"}


def _create_owner(client: TestClient) -> str:
    resp = client.post(
        "/api/auth/setup",
        json={
            "name": "Guard Test Owner",
            "email": "guardtest@example.com",
            "preferred_language": "bn",
            "secret_word": "testsecret",
        },
    )
    assert resp.status_code == 201
    return resp.json()["owner_id"]


def _mock_guard_no_challenge() -> AsyncMock:
    """Mock guard that always returns no challenge."""
    guard = AsyncMock()
    guard.check = AsyncMock(return_value=GuardCheckResult(
        suspicion_score=5,
        challenge_level=ChallengeLevel.none,
        anomalies=[],
    ))
    guard.evaluate_challenge = AsyncMock()
    guard.reset_score = AsyncMock()
    return guard


def _mock_guard_soft_challenge() -> AsyncMock:
    """Mock guard that returns a soft challenge."""
    from app.models.identity import ChallengePayload

    guard = AsyncMock()
    guard.check = AsyncMock(return_value=GuardCheckResult(
        suspicion_score=45,
        challenge_level=ChallengeLevel.soft,
        anomalies=["language_switch (+20)", "sensitive_topic (+25)"],
        challenge=ChallengePayload(
            challenge_id="challenge-soft-1",
            challenge_type=ChallengeLevel.soft,
            question="What's the name of your cat?",
            timeout_seconds=60,
        ),
    ))
    guard.evaluate_challenge = AsyncMock()
    return guard


def _mock_guard_hard_challenge() -> AsyncMock:
    """Mock guard that returns a hard challenge."""
    from app.models.identity import ChallengePayload

    guard = AsyncMock()
    guard.check = AsyncMock(return_value=GuardCheckResult(
        suspicion_score=70,
        challenge_level=ChallengeLevel.hard,
        anomalies=["failed_verification (+30)", "sensitive_topic (+25)", "typing_anomaly (+15)"],
        challenge=ChallengePayload(
            challenge_id="challenge-hard-1",
            challenge_type=ChallengeLevel.hard,
            methods=["secret_word", "voice_match"],
            timeout_seconds=120,
        ),
    ))
    guard.evaluate_challenge = AsyncMock()
    return guard


def _mock_guard_lockout() -> AsyncMock:
    """Mock guard that returns lockout."""
    guard = AsyncMock()
    guard.check = AsyncMock(return_value=GuardCheckResult(
        suspicion_score=90,
        challenge_level=ChallengeLevel.lockout,
        anomalies=["already_locked_out"],
    ))
    return guard


def _mock_rag() -> AsyncMock:
    rag = AsyncMock()
    rag.generate_grounded_response = AsyncMock(return_value={
        "response": "Hello from the AI.",
        "sources": [],
        "query_used": "greeting",
    })
    return rag


def _mock_conv() -> AsyncMock:
    conv = AsyncMock()
    mock_thread = MagicMock()
    mock_thread.id = "thread-guard"
    mock_thread.owner_id = OWNER_ID
    conv.get_or_create_thread = AsyncMock(return_value=mock_thread)

    call_count = 0
    async def fake_save_message(**kwargs):
        nonlocal call_count
        call_count += 1
        msg = MagicMock()
        msg.id = f"msg-guard-{call_count}"
        msg.thread_id = kwargs.get("thread_id", "thread-guard")
        msg.role = kwargs.get("role")
        msg.content_text = kwargs.get("content", "")
        msg.created_at = datetime(2026, 1, 1)
        return msg
    conv.save_message = AsyncMock(side_effect=fake_save_message)
    conv.load_context = AsyncMock(return_value=[])
    conv.build_system_prompt = MagicMock(return_value="You are an AI replica.")
    conv.maybe_summarize = AsyncMock()
    conv.list_threads = AsyncMock(return_value=([], 0))
    conv.get_messages = AsyncMock(return_value=([], False))
    return conv


def _mock_ingestor() -> AsyncMock:
    ingestor = AsyncMock()
    ingestor.ingest_text = AsyncMock(return_value="entry-ingested-1")
    return ingestor


def _override_all(
    guard: AsyncMock,
    rag: AsyncMock | None = None,
    conv: AsyncMock | None = None,
    ingestor: AsyncMock | None = None,
) -> None:
    from app.main import app
    app.dependency_overrides[_get_identity_guard] = lambda: guard
    if rag is not None:
        app.dependency_overrides[_get_rag_engine] = lambda: rag
    if conv is not None:
        app.dependency_overrides[_get_conversation_manager] = lambda: conv
    if ingestor is not None:
        app.dependency_overrides[_get_ingestor] = lambda: ingestor


def _clear_overrides() -> None:
    from app.main import app
    app.dependency_overrides.pop(_get_identity_guard, None)
    app.dependency_overrides.pop(_get_rag_engine, None)
    app.dependency_overrides.pop(_get_conversation_manager, None)
    app.dependency_overrides.pop(_get_ingestor, None)


# ─── Tests: Normal flow (no challenge) ──────────────────


def test_chat_message_passes_guard_check(client: TestClient) -> None:
    """Normal message goes through when guard returns no challenge."""
    owner_id = _create_owner(client)
    guard = _mock_guard_no_challenge()
    rag = _mock_rag()
    conv = _mock_conv()
    ingestor = _mock_ingestor()
    _override_all(guard, rag, conv, ingestor)

    resp = client.post(
        "/api/chat/message",
        json={"message": "Hello, how are you doing today?"},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "Hello from the AI."

    # Guard check was called
    guard.check.assert_called_once()
    call_kwargs = guard.check.call_args.kwargs
    assert call_kwargs["owner_id"] == owner_id
    assert call_kwargs["message"] == "Hello, how are you doing today?"
    assert call_kwargs["role"] == "owner"

    _clear_overrides()


# ─── Tests: Soft challenge ───────────────────────────────


def test_chat_message_soft_challenge_returns_428(client: TestClient) -> None:
    """When guard triggers soft challenge, REST returns 428 with challenge info."""
    owner_id = _create_owner(client)
    guard = _mock_guard_soft_challenge()
    _override_all(guard)

    resp = client.post(
        "/api/chat/message",
        json={"message": "Tell me about my bank account password."},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 428
    data = resp.json()["detail"]
    assert data["challenge_required"] is True
    assert data["challenge_type"] == "soft"
    assert data["challenge_id"] == "challenge-soft-1"
    assert data["question"] == "What's the name of your cat?"
    assert data["timeout_seconds"] == 60

    _clear_overrides()


# ─── Tests: Hard challenge ───────────────────────────────


def test_chat_message_hard_challenge_returns_428(client: TestClient) -> None:
    """When guard triggers hard challenge, REST returns 428 with methods."""
    owner_id = _create_owner(client)
    guard = _mock_guard_hard_challenge()
    _override_all(guard)

    resp = client.post(
        "/api/chat/message",
        json={"message": "What's the credit card number?"},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 428
    data = resp.json()["detail"]
    assert data["challenge_required"] is True
    assert data["challenge_type"] == "hard"
    assert "secret_word" in data["methods"]
    assert "voice_match" in data["methods"]
    assert data["timeout_seconds"] == 120

    _clear_overrides()


# ─── Tests: Lockout ──────────────────────────────────────


def test_chat_message_lockout_returns_403(client: TestClient) -> None:
    """When guard triggers lockout, REST returns 403."""
    owner_id = _create_owner(client)
    guard = _mock_guard_lockout()
    _override_all(guard)

    resp = client.post(
        "/api/chat/message",
        json={"message": "Hello"},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 403
    assert "locked" in resp.json()["detail"].lower()

    _clear_overrides()


# ─── Tests: Challenge response endpoint ──────────────────


def test_challenge_response_success(client: TestClient) -> None:
    """Challenge response endpoint evaluates and returns result."""
    from app.models.identity import ChallengeResult

    owner_id = _create_owner(client)
    guard = AsyncMock()
    guard.evaluate_challenge = AsyncMock(return_value=ChallengeResult(
        passed=True,
        message="Challenge passed. Identity confirmed.",
        new_score=10,
    ))
    _override_all(guard)

    resp = client.post(
        "/api/chat/challenge",
        json={
            "challenge_id": "challenge-soft-1",
            "answer": "Whiskers",
        },
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert data["new_score"] == 10
    guard.evaluate_challenge.assert_called_once()

    _clear_overrides()


def test_challenge_response_failure(client: TestClient) -> None:
    """Failed challenge response returns passed=false."""
    from app.models.identity import ChallengeResult

    owner_id = _create_owner(client)
    guard = AsyncMock()
    guard.evaluate_challenge = AsyncMock(return_value=ChallengeResult(
        passed=False,
        message="Challenge failed.",
        new_score=65,
    ))
    _override_all(guard)

    resp = client.post(
        "/api/chat/challenge",
        json={
            "challenge_id": "challenge-soft-1",
            "answer": "Wrong answer",
        },
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is False
    assert data["new_score"] == 65

    _clear_overrides()


def test_challenge_endpoint_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/chat/challenge",
        json={"challenge_id": "test", "answer": "test"},
    )
    assert resp.status_code == 401 or resp.status_code == 403


# ─── Tests: IdentityGuard scoring logic ─────────────────


def test_sensitive_topic_detection() -> None:
    """Sensitive topic keywords should be detected."""
    from app.services.identity_guard import IdentityGuard

    guard = IdentityGuard.__new__(IdentityGuard)
    score, detail = guard._check_sensitive_topic("What's my credit card number and bank account?")
    assert score > 0
    assert "credit card" in detail.lower()


def test_sensitive_topic_normal_message() -> None:
    """Normal messages should not trigger sensitive topic detection."""
    from app.services.identity_guard import IdentityGuard

    guard = IdentityGuard.__new__(IdentityGuard)
    score, detail = guard._check_sensitive_topic("Tell me about the weather today.")
    assert score == 0
    assert detail == ""


def test_unusual_hours_detection() -> None:
    """Unusual hours detector should flag 1am-5am UTC."""
    from app.services.identity_guard import _is_unusual_hour

    assert _is_unusual_hour(2) is True
    assert _is_unusual_hour(3) is True
    assert _is_unusual_hour(0) is False
    assert _is_unusual_hour(6) is False
    assert _is_unusual_hour(14) is False


def test_challenge_level_thresholds() -> None:
    """Verify the scoring thresholds map to correct challenge levels."""
    from app.services.identity_guard import (
        THRESHOLD_HARD,
        THRESHOLD_LOCKOUT,
        THRESHOLD_SOFT,
    )

    assert THRESHOLD_SOFT == 30
    assert THRESHOLD_HARD == 60
    assert THRESHOLD_LOCKOUT == 80


# ─── Tests: Guard skips non-owner roles ──────────────────


def test_guard_skips_family_members(client: TestClient) -> None:
    """Family member messages should bypass the identity guard."""
    owner_id = _create_owner(client)
    guard = AsyncMock()
    guard.check = AsyncMock(return_value=GuardCheckResult(
        suspicion_score=0,
        challenge_level=ChallengeLevel.none,
    ))
    rag = _mock_rag()
    conv = _mock_conv()
    ingestor = _mock_ingestor()
    _override_all(guard, rag, conv, ingestor)

    family_token = create_access_token(subject=owner_id, role="family_member")
    headers = {"Authorization": f"Bearer {family_token}"}

    resp = client.post(
        "/api/chat/message",
        json={"message": "Tell me about credit card details."},
        headers=headers,
    )
    assert resp.status_code == 200

    # Guard was called but role was "family_member" — should return no challenge
    guard.check.assert_called_once()
    call_kwargs = guard.check.call_args.kwargs
    assert call_kwargs["role"] == "family_member"

    _clear_overrides()
