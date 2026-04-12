"""Tests for the search router (proxied to AI service via ai_client)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.security import create_access_token


# -- Helpers --


OWNER_ID = "owner-search-123"


def _auth_header(owner_id: str = OWNER_ID) -> dict[str, str]:
    token = create_access_token(subject=owner_id, role="owner")
    return {"Authorization": f"Bearer {token}"}


def _mock_vector_search_response(n: int = 2) -> dict:
    results = []
    for i in range(n):
        results.append({
            "entry_id": f"entry-{i}",
            "content_type": "text",
            "score": 0.95 - (i * 0.1),
            "content_preview": f"Sample content {i}",
            "original_language": "en",
            "chunk_index": 0,
        })
    return {"query": "test", "results": results, "total": n}


# -- POST /api/search --


def test_search_requires_auth(client) -> None:
    resp = client.post(
        "/api/search",
        json={"query": "test"},
    )
    assert resp.status_code == 401


def test_search_empty_query(client) -> None:
    resp = client.post(
        "/api/search",
        json={"query": ""},
        headers=_auth_header(),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_success(client) -> None:
    mock_ai = AsyncMock()
    mock_ai.vector_search = AsyncMock(return_value=_mock_vector_search_response())

    with patch("app.routers.search.get_ai_client", return_value=mock_ai):
        from app.main import app
        from app.core.ai_client import get_ai_client
        app.dependency_overrides[get_ai_client] = lambda: mock_ai

        resp = client.post(
            "/api/search",
            json={"query": "What is my favorite food?"},
            headers=_auth_header(),
        )

        app.dependency_overrides.pop(get_ai_client, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "What is my favorite food?"
    assert data["total"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["entry_id"] == "entry-0"
    assert data["results"][0]["score"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_search_empty_results(client) -> None:
    mock_ai = AsyncMock()
    mock_ai.vector_search = AsyncMock(
        return_value={"query": "test", "results": [], "total": 0}
    )

    from app.main import app
    from app.core.ai_client import get_ai_client
    app.dependency_overrides[get_ai_client] = lambda: mock_ai

    resp = client.post(
        "/api/search",
        json={"query": "something obscure"},
        headers=_auth_header(),
    )

    app.dependency_overrides.pop(get_ai_client, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []
