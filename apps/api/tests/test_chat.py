import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.chat import (
    ChatMessageResponse,
    ConversationThread,
    Message,
    MessageRole,
    ParticipantType,
)
from app.routers.chat import (
    _get_conversation_manager,
    _get_ingestor,
    _get_rag_engine,
)


# ─── Helpers ─────────────────────────────────────────────


OWNER_ID = "owner-chat-123"


def _owner_token(owner_id: str = OWNER_ID) -> str:
    return create_access_token(subject=owner_id, role="owner")


def _auth_header(owner_id: str = OWNER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_owner_token(owner_id)}"}


def _family_token(owner_id: str = OWNER_ID) -> str:
    return create_access_token(subject=owner_id, role="family_member")


def _family_auth_header(owner_id: str = OWNER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_family_token(owner_id)}"}


def _mock_rag() -> AsyncMock:
    rag = AsyncMock()
    rag.generate_grounded_response = AsyncMock(return_value={
        "response": "Hello! I'm your AI replica.",
        "sources": [],
        "query_used": "greeting",
    })
    return rag


def _mock_conv() -> AsyncMock:
    conv = AsyncMock()

    # get_or_create_thread returns a mock thread
    mock_thread = MagicMock()
    mock_thread.id = "thread-abc"
    mock_thread.owner_id = OWNER_ID
    mock_thread.participant_type = ParticipantType.owner
    mock_thread.participant_name = "owner"
    mock_thread.created_at = datetime(2026, 1, 1)
    conv.get_or_create_thread = AsyncMock(return_value=mock_thread)

    # save_message returns mock messages
    call_count = 0
    async def fake_save_message(**kwargs):
        nonlocal call_count
        call_count += 1
        msg = MagicMock()
        msg.id = f"msg-{call_count}"
        msg.thread_id = kwargs.get("thread_id", "thread-abc")
        msg.role = kwargs.get("role", MessageRole.user)
        msg.content_text = kwargs.get("content", "")
        msg.language = kwargs.get("language", "en")
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


def _create_owner(client: TestClient) -> str:
    resp = client.post(
        "/api/auth/setup",
        json={
            "name": "Chat Test Owner",
            "email": "chattest@example.com",
            "preferred_language": "en",
            "secret_word": "testsecret",
        },
    )
    assert resp.status_code == 201
    return resp.json()["owner_id"]


def _override_all(rag: AsyncMock, conv: AsyncMock, ingestor: AsyncMock) -> None:
    from app.main import app
    app.dependency_overrides[_get_rag_engine] = lambda: rag
    app.dependency_overrides[_get_conversation_manager] = lambda: conv
    app.dependency_overrides[_get_ingestor] = lambda: ingestor


def _clear_overrides() -> None:
    from app.main import app
    app.dependency_overrides.pop(_get_rag_engine, None)
    app.dependency_overrides.pop(_get_conversation_manager, None)
    app.dependency_overrides.pop(_get_ingestor, None)


# ─── POST /api/chat/message ─────────────────────────────


def test_chat_message_success(client: TestClient) -> None:
    owner_id = _create_owner(client)
    rag = _mock_rag()
    conv = _mock_conv()
    ingestor = _mock_ingestor()
    _override_all(rag, conv, ingestor)

    resp = client.post(
        "/api/chat/message",
        json={"message": "Hello, this is a long enough message to trigger learning."},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "thread-abc"
    assert data["response"] == "Hello! I'm your AI replica."
    assert "message_id" in data

    # Verify RAG was called
    rag.generate_grounded_response.assert_called_once()

    _clear_overrides()


def test_chat_message_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/chat/message",
        json={"message": "Hello"},
    )
    assert resp.status_code == 401


def test_chat_message_empty_body(client: TestClient) -> None:
    resp = client.post(
        "/api/chat/message",
        json={"message": ""},
        headers=_auth_header(),
    )
    assert resp.status_code == 422


def test_chat_message_with_thread_id(client: TestClient) -> None:
    owner_id = _create_owner(client)
    rag = _mock_rag()
    conv = _mock_conv()
    ingestor = _mock_ingestor()
    _override_all(rag, conv, ingestor)

    resp = client.post(
        "/api/chat/message",
        json={"message": "Hello again, continuing our long conversation.", "thread_id": "thread-existing"},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200

    # Check that get_or_create_thread was called with the thread_id
    call_kwargs = conv.get_or_create_thread.call_args
    assert call_kwargs.kwargs.get("thread_id") == "thread-existing"

    _clear_overrides()


def test_chat_message_family_member(client: TestClient) -> None:
    owner_id = _create_owner(client)
    rag = _mock_rag()
    conv = _mock_conv()
    ingestor = _mock_ingestor()
    _override_all(rag, conv, ingestor)

    resp = client.post(
        "/api/chat/message",
        json={"message": "Tell me about the owner's favorite food please."},
        headers=_family_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "Hello! I'm your AI replica."
    # Family member should NOT trigger knowledge ingestion
    assert data["is_learning"] is False

    _clear_overrides()


def test_chat_owner_triggers_learning(client: TestClient) -> None:
    owner_id = _create_owner(client)
    rag = _mock_rag()
    conv = _mock_conv()
    ingestor = _mock_ingestor()
    _override_all(rag, conv, ingestor)

    resp = client.post(
        "/api/chat/message",
        json={"message": "My favorite color is blue and I love hiking in the mountains."},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_learning"] is True
    ingestor.ingest_text.assert_called_once()

    _clear_overrides()


# ─── GET /api/chat/threads ──────────────────────────────


def test_list_threads_empty(client: TestClient) -> None:
    conv = _mock_conv()
    from app.main import app
    app.dependency_overrides[_get_conversation_manager] = lambda: conv

    resp = client.get("/api/chat/threads", headers=_auth_header())
    assert resp.status_code == 200
    data = resp.json()
    assert data["threads"] == []
    assert data["total"] == 0

    app.dependency_overrides.pop(_get_conversation_manager, None)


def test_list_threads_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/chat/threads")
    assert resp.status_code == 401


# ─── GET /api/chat/threads/{id}/messages ─────────────────


def test_get_messages_empty(client: TestClient) -> None:
    conv = _mock_conv()
    from app.main import app
    app.dependency_overrides[_get_conversation_manager] = lambda: conv

    resp = client.get("/api/chat/threads/thread-abc/messages", headers=_auth_header())
    assert resp.status_code == 200
    data = resp.json()
    assert data["messages"] == []
    assert data["thread_id"] == "thread-abc"
    assert data["has_more"] is False

    app.dependency_overrides.pop(_get_conversation_manager, None)


def test_get_messages_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/chat/threads/thread-abc/messages")
    assert resp.status_code == 401


# ──��� WebSocket /ws/chat/{owner_id} ──────────────────────


def test_websocket_auth_via_query_param(client: TestClient) -> None:
    """WebSocket should accept auth via token query param."""
    owner_id = _create_owner(client)
    token = _owner_token(owner_id)

    with client.websocket_connect(f"/ws/chat/{owner_id}?token={token}") as ws:
        data = ws.receive_json()
        assert data["type"] == "auth_ok"
        assert data["owner_id"] == owner_id


def test_websocket_auth_via_first_message(client: TestClient) -> None:
    """WebSocket should accept auth via first JSON message."""
    owner_id = _create_owner(client)
    token = _owner_token(owner_id)

    with client.websocket_connect(f"/ws/chat/{owner_id}") as ws:
        ws.send_json({"type": "auth", "token": token})
        data = ws.receive_json()
        assert data["type"] == "auth_ok"


def test_websocket_rejects_bad_token(client: TestClient) -> None:
    """WebSocket should close with error for invalid token."""
    with client.websocket_connect("/ws/chat/some-owner?token=bad-token") as ws:
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "Invalid token" in data["detail"]


def test_websocket_rejects_mismatched_owner(client: TestClient) -> None:
    """WebSocket should reject when token owner doesn't match URL owner_id."""
    owner_id = _create_owner(client)
    token = _owner_token(owner_id)

    with client.websocket_connect(f"/ws/chat/different-owner?token={token}") as ws:
        data = ws.receive_json()
        assert data["type"] == "error"
        assert "mismatch" in data["detail"].lower()
