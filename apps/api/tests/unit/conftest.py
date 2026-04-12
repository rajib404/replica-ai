"""Fixtures for pure unit tests.

Unit tests must not touch PostgreSQL, Redis, Qdrant, Ollama, or the
filesystem beyond tmpdirs. Everything external is mocked here.

All tests in this directory are auto-marked with ``@pytest.mark.unit``
via ``pytest_collection_modifyitems``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-tag everything under tests/unit with the ``unit`` marker."""
    for item in items:
        if "/tests/unit/" in str(item.fspath) or "\\tests\\unit\\" in str(item.fspath):
            item.add_marker(pytest.mark.unit)


# ─── Mocked AI service client ───────────────────────────────


@pytest.fixture
def mock_ai_client() -> AsyncMock:
    """A stand-in for ``AIServiceClient`` with canned responses for
    every method used by routers and services."""
    ai = AsyncMock()
    ai.health = AsyncMock(
        return_value={
            "status": "ok",
            "ollama": {"status": "ok"},
            "qdrant": {"status": "ok"},
        }
    )
    ai.health_safe = AsyncMock(return_value={"status": "ok"})
    ai.generate = AsyncMock(
        return_value={"response": "hello from mock", "model": "mistral"}
    )
    ai.embed = AsyncMock(return_value={"embedding": [0.1] * 384})
    ai.rag_search = AsyncMock(return_value={"results": []})
    ai.rag_generate = AsyncMock(
        return_value={
            "response": "mock rag response",
            "sources": [{"id": "k1", "score": 0.9, "text": "fact"}],
        }
    )
    ai.ingest_text = AsyncMock(return_value={"id": "k-mock-1", "status": "ingested"})
    ai.ingest_audio = AsyncMock(return_value={"id": "k-mock-2", "status": "ingested"})
    ai.ingest_video = AsyncMock(return_value={"id": "k-mock-3", "status": "ingested"})
    ai.ingest_document = AsyncMock(return_value={"id": "k-mock-4", "status": "ingested"})
    ai.list_models = AsyncMock(return_value={"models": [{"name": "mistral:7b"}]})
    ai.pull_model = AsyncMock(return_value={"status": "pulled"})
    return ai


# ─── Mocked SQLAlchemy session ──────────────────────────────


class _FakeScalarResult:
    def __init__(self, value: Any):
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        if self._value is None:
            raise RuntimeError("No row")
        return self._value

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return self._value
        return [self._value]

    def first(self) -> Any:
        if isinstance(self._value, list):
            return self._value[0] if self._value else None
        return self._value


@pytest.fixture
def mock_db() -> AsyncMock:
    """A minimally-functional ``AsyncSession`` mock.

    ``.execute`` returns a ``_FakeScalarResult``. Tests that need a
    specific row should configure the return value on a per-test basis
    via ``mock_db.execute.return_value = _FakeScalarResult(row)``.
    """
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_FakeScalarResult(None))
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def fake_scalar():
    """Helper to construct a fake SQLAlchemy result."""
    return _FakeScalarResult


# ─── Mocked Qdrant ──────────────────────────────────────────


@pytest.fixture
def mock_qdrant() -> MagicMock:
    q = MagicMock()
    q.search = MagicMock(return_value=[])
    q.upsert = MagicMock()
    q.delete = MagicMock()
    q.get_collections = MagicMock(return_value=MagicMock(collections=[]))
    return q


# ─── Sample data factories ──────────────────────────────────


@pytest.fixture
def sample_owner_dict() -> dict[str, Any]:
    return {
        "id": "owner_test_1",
        "name": "Alice Test",
        "email": "alice@example.test",
        "phone": None,
        "preferred_language": "en",
        "created_at": datetime.now(UTC).replace(tzinfo=None),
        "updated_at": datetime.now(UTC).replace(tzinfo=None),
    }


@pytest.fixture
def sample_conversation_history() -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "Hi, how are you?"},
        {"role": "assistant", "content": "I'm well, thanks!"},
        {"role": "user", "content": "What's the weather like?"},
    ]
