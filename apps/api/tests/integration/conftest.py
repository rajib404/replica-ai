"""Integration test fixtures.

Integration tests run against the real FastAPI app + a real Postgres DB,
but with all *external* services (AI service, Ollama, Qdrant, Redis) replaced
by AsyncMock instances. This gives us end-to-end coverage of routing, auth,
DB writes, response shapes, and error envelopes — without needing the entire
docker-compose stack to be up.

Tests in this directory are automatically tagged with ``@pytest.mark.integration``
so they can be selected/excluded via ``pytest -m integration``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock

import pytest


# ─── Auto-tag every test in this directory ──────────────────


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    integration_marker = pytest.mark.integration
    for item in items:
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(integration_marker)


# ─── AI service client mock ─────────────────────────────────


@pytest.fixture
def mock_ai_client() -> AsyncMock:
    """A fully mocked ``AIServiceClient`` with pre-canned responses for the
    most-used methods.

    Tests can override individual return values per-test via
    ``mock_ai_client.rag_generate.return_value = {...}``.
    """
    ai = AsyncMock()

    ai.health = AsyncMock(
        return_value={"status": "ok", "ollama": {"status": "ok"}}
    )
    ai.health_safe = AsyncMock(
        return_value={"status": "ok", "ollama": {"status": "ok"}}
    )

    ai.list_models = AsyncMock(
        return_value={"models": [{"name": "mistral:7b"}]}
    )
    ai.pull_model = AsyncMock(return_value={"status": "ok"})

    ai.generate = AsyncMock(
        return_value={"response": "ok", "model": "mistral:7b"}
    )
    ai.embed = AsyncMock(return_value={"embedding": [0.0] * 384})

    # Knowledge ingestion
    def _ingest_text_response(**kwargs: Any) -> dict:
        return {
            "entry_id": "entry-text-1",
            "embedding_id": "vec-1",
            "language": kwargs.get("language", "en"),
            "english_translation": kwargs.get("english_translation"),
            "metadata": {"source": "text"},
        }

    ai.ingest_text = AsyncMock(side_effect=_ingest_text_response)
    ai.ingest_audio = AsyncMock(return_value={"task_id": "task-audio-1"})
    ai.ingest_video = AsyncMock(return_value={"task_id": "task-video-1"})
    ai.ingest_document = AsyncMock(return_value={"task_id": "task-doc-1"})

    # Task status — completed by default
    ai.get_task_status = AsyncMock(
        return_value={
            "task_id": "task-doc-1",
            "status": "completed",
            "owner_id": "WILL-BE-OVERRIDDEN",
            "result": None,
        }
    )

    # RAG
    ai.rag_search = AsyncMock(return_value={"results": []})
    ai.rag_generate = AsyncMock(
        return_value={
            "response": "I understand. Tell me more.",
            "sources": [],
            "model": "mistral:7b",
        }
    )

    async def _empty_stream(*args: Any, **kwargs: Any):
        for event in [
            {"type": "sources", "sources": []},
            {"type": "token", "token": "Hello"},
            {"type": "token", "token": " there"},
            {"type": "done"},
        ]:
            yield event

    ai.rag_stream = _empty_stream

    ai.delete_vectors = AsyncMock(return_value={"deleted": True})

    return ai


@pytest.fixture
def client_with_ai(client, mock_ai_client: AsyncMock):  # noqa: ANN001
    """A ``TestClient`` with the AI service dependency replaced by a mock."""
    from app.core.ai_client import get_ai_client
    from app.main import app

    app.dependency_overrides[get_ai_client] = lambda: mock_ai_client
    yield client
    app.dependency_overrides.pop(get_ai_client, None)


# ─── Authenticated owner helper ─────────────────────────────


@pytest.fixture
def authed_owner(client_with_ai) -> Generator[dict, None, None]:  # noqa: ANN001
    """Create a fresh owner via the real /api/auth/setup flow.

    Returns a dict with ``owner_id``, ``access_token``, ``refresh_token``,
    and a ``headers`` shortcut.
    """
    response = client_with_ai.post(
        "/api/auth/setup",
        json={
            "name": "Integration Owner",
            "email": "integration@example.com",
            "preferred_language": "en",
            "secret_word": "integrationsecret",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    yield {
        "client": client_with_ai,
        "owner_id": data["owner_id"],
        "access_token": data["tokens"]["access_token"],
        "refresh_token": data["tokens"]["refresh_token"],
        "headers": {
            "Authorization": f"Bearer {data['tokens']['access_token']}"
        },
    }
