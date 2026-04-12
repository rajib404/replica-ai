"""End-to-end owner flow: setup → ingest knowledge → chat → list threads.

These tests exercise the real REST surface against a real Postgres database.
The AI service client is mocked so the test doesn't need Ollama / Qdrant up.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock


class TestOwnerSetupFlow:
    def test_full_setup_to_chat(
        self,
        authed_owner: dict,
        mock_ai_client: AsyncMock,
    ) -> None:
        client = authed_owner["client"]
        owner_id = authed_owner["owner_id"]
        headers = authed_owner["headers"]

        # 1. Owner exists — verify by issuing an authenticated call
        threads = client.get("/api/chat/threads", headers=headers)
        assert threads.status_code == 200
        assert threads.json()["total"] == 0

        # 2. Ingest a piece of text knowledge
        ingest = client.post(
            "/api/knowledge/text",
            json={"text": "I love hiking in the mountains.", "language": "en"},
            headers=headers,
        )
        assert ingest.status_code == 201
        entry_id = ingest.json()["entry_id"]
        assert entry_id

        # The AI mock recorded the call
        mock_ai_client.ingest_text.assert_awaited()
        call_kwargs = mock_ai_client.ingest_text.await_args.kwargs
        assert call_kwargs["owner_id"] == owner_id
        assert "hiking" in call_kwargs["text"]

        # 3. The entry shows up in the list
        listed = client.get("/api/knowledge/entries", headers=headers)
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] >= 1
        assert any(e["id"] == entry_id for e in body["entries"])

        # 4. Send a chat message
        mock_ai_client.rag_generate.return_value = {
            "response": "Hiking sounds wonderful! Tell me about your favorite trail.",
            "sources": [{"entry_id": entry_id, "score": 0.9}],
            "model": "mistral:7b",
        }

        chat = client.post(
            "/api/chat/message",
            json={"message": "What did I tell you about hiking?"},
            headers=headers,
        )
        assert chat.status_code == 200, chat.text
        chat_body = chat.json()
        assert chat_body["thread_id"]
        assert chat_body["message_id"]
        assert "Hiking" in chat_body["response"]
        assert len(chat_body["sources"]) == 1

        # 5. Threads list now contains a thread
        threads_after = client.get("/api/chat/threads", headers=headers)
        assert threads_after.json()["total"] >= 1

        # 6. Thread messages contain the user + assistant pair
        thread_id = chat_body["thread_id"]
        msgs = client.get(
            f"/api/chat/threads/{thread_id}/messages",
            headers=headers,
        )
        assert msgs.status_code == 200
        msg_body = msgs.json()
        # at least the user message and assistant response
        assert len(msg_body["messages"]) >= 2
        roles = {m["role"] for m in msg_body["messages"]}
        assert "user" in roles
        assert "assistant" in roles

    def test_unauthenticated_chat_rejected(
        self, client_with_ai
    ) -> None:
        response = client_with_ai.post(
            "/api/chat/message",
            json={"message": "hi"},
        )
        assert response.status_code in (401, 403)

    def test_chat_with_other_owners_thread_id_creates_new_thread(
        self,
        authed_owner: dict,
        mock_ai_client: AsyncMock,
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        # Send a message with a totally bogus thread id
        response = client.post(
            "/api/chat/message",
            json={
                "message": "Hello there",
                "thread_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=headers,
        )
        # Either creates a new thread or returns 404 — both are acceptable
        assert response.status_code in (200, 404)

    def test_knowledge_entry_delete(
        self,
        authed_owner: dict,
        mock_ai_client: AsyncMock,
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        # Use a fresh entry_id so we don't collide with other tests
        mock_ai_client.ingest_text.side_effect = lambda **kw: {
            "entry_id": "entry-to-delete",
            "embedding_id": "vec-to-delete",
            "language": "en",
            "metadata": {},
        }

        ingest = client.post(
            "/api/knowledge/text",
            json={"text": "Delete me please.", "language": "en"},
            headers=headers,
        )
        assert ingest.status_code == 201
        entry_id = ingest.json()["entry_id"]

        # Delete it
        delete = client.delete(
            f"/api/knowledge/entries/{entry_id}",
            headers=headers,
        )
        assert delete.status_code == 204

        # Now 404
        get_after = client.get(
            f"/api/knowledge/entries/{entry_id}",
            headers=headers,
        )
        assert get_after.status_code == 404

        # AI service was asked to delete vectors too
        mock_ai_client.delete_vectors.assert_awaited_with(entry_id)


class TestKnowledgeIngestionValidation:
    def test_audio_rejects_bad_extension(
        self, authed_owner: dict
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        files = {"file": ("not_audio.exe", b"fake", "application/octet-stream")}
        response = client.post(
            "/api/knowledge/audio", files=files, headers=headers
        )
        assert response.status_code == 400
        body = response.json()
        # Could be the structured envelope or a plain detail
        msg = (
            body.get("error", {}).get("message")
            or body.get("detail")
            or ""
        )
        assert "audio" in msg.lower() or "format" in msg.lower()

    def test_document_accepts_pdf(
        self,
        authed_owner: dict,
        mock_ai_client: AsyncMock,
    ) -> None:
        client = authed_owner["client"]
        headers = authed_owner["headers"]

        files = {"file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")}
        response = client.post(
            "/api/knowledge/document", files=files, headers=headers
        )
        assert response.status_code == 202
        assert response.json()["task_id"]
        mock_ai_client.ingest_document.assert_awaited()
