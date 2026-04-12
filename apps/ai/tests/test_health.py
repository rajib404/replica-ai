from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Replica AI Service"}


@pytest.mark.asyncio
async def test_health_endpoint():
    with (
        patch("app.routers.health.OllamaClient") as MockOllama,
        patch("app.routers.health.get_qdrant") as mock_get_qdrant,
    ):
        mock_ollama = MockOllama.return_value
        mock_ollama.health_check = AsyncMock(
            return_value={"status": "ok", "ollama_response": "Ollama is running"}
        )

        mock_qdrant = AsyncMock()
        mock_qdrant.health_check = AsyncMock(return_value=True)
        mock_get_qdrant.return_value = mock_qdrant

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
