"""Unit tests for ``AIServiceClient`` using ``respx`` to mock HTTP.

These tests exercise the client end-to-end through the real httpx layer
but against a mocked transport — so we can verify that the retry
decorator actually takes effect and that error translations happen.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.ai_client import AIServiceClient
from app.core.exceptions import ModelUnavailableError


BASE_URL = "http://ai-test.local"


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink retry delays so exhaustion tests run fast."""
    from app.core import retry as retry_mod

    monkeypatch.setattr(retry_mod.settings, "retry_ollama_attempts", 3)
    monkeypatch.setattr(retry_mod.settings, "retry_ollama_backoff_base", 0.001)
    monkeypatch.setattr(retry_mod.settings, "retry_ollama_backoff_max", 0.002)


@pytest.fixture
async def ai() -> AIServiceClient:
    client = AIServiceClient(base_url=BASE_URL)
    try:
        yield client
    finally:
        await client.close()


@respx.mock
async def test_health_success(ai: AIServiceClient) -> None:
    respx.get(f"{BASE_URL}/health").respond(
        200, json={"status": "ok", "ollama": {"status": "ok"}}
    )

    result = await ai.health()
    assert result["status"] == "ok"


@respx.mock
async def test_health_safe_returns_unreachable_on_connect_error(
    ai: AIServiceClient,
) -> None:
    respx.get(f"{BASE_URL}/health").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    result = await ai.health_safe()
    assert result["status"] == "unreachable"
    assert "AI service" in result["error"]


@respx.mock
async def test_health_safe_returns_timeout_on_timeout(
    ai: AIServiceClient,
) -> None:
    respx.get(f"{BASE_URL}/health").mock(
        side_effect=httpx.ConnectTimeout("slow")
    )

    result = await ai.health_safe()
    assert result["status"] == "timeout"


@respx.mock
async def test_list_models_success(ai: AIServiceClient) -> None:
    respx.get(f"{BASE_URL}/models").respond(
        200, json={"models": [{"name": "mistral:7b"}]}
    )

    result = await ai.list_models()
    assert len(result["models"]) == 1


@respx.mock
async def test_list_models_retries_then_succeeds(ai: AIServiceClient) -> None:
    """Transient ConnectError should be retried and the second call returns."""
    route = respx.get(f"{BASE_URL}/models")
    route.side_effect = [
        httpx.ConnectError("boom"),
        httpx.Response(200, json={"models": []}),
    ]

    result = await ai.list_models()
    assert result == {"models": []}
    assert route.call_count == 2


@respx.mock
async def test_list_models_exhausts_retries_raises_model_unavailable(
    ai: AIServiceClient,
) -> None:
    respx.get(f"{BASE_URL}/models").mock(
        side_effect=httpx.ConnectError("still dead")
    )

    with pytest.raises(ModelUnavailableError) as exc_info:
        await ai.list_models()
    assert exc_info.value.details["attempts"] == 3


@respx.mock
async def test_500_from_ollama_becomes_model_unavailable(
    ai: AIServiceClient,
) -> None:
    respx.get(f"{BASE_URL}/models").respond(500, json={"error": "internal"})

    with pytest.raises(ModelUnavailableError) as exc_info:
        await ai.list_models()
    assert exc_info.value.details.get("status") == 500


@respx.mock
async def test_404_is_not_rewrapped(ai: AIServiceClient) -> None:
    respx.get(f"{BASE_URL}/models").respond(404, json={"error": "not found"})

    with pytest.raises(httpx.HTTPStatusError):
        await ai.list_models()


@respx.mock
async def test_generate_happy_path(ai: AIServiceClient) -> None:
    respx.post(f"{BASE_URL}/generate").respond(
        200, json={"response": "hi", "model": "mistral"}
    )

    result = await ai.generate(prompt="hello")
    assert result["response"] == "hi"


@respx.mock
async def test_rag_generate_happy_path(ai: AIServiceClient) -> None:
    respx.post(f"{BASE_URL}/rag/generate").respond(
        200, json={"response": "ok", "sources": []}
    )

    result = await ai.rag_generate(
        owner_id="o1",
        message="hi",
        conversation_history=[],
    )
    assert result["response"] == "ok"
