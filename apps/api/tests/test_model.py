from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.routers.model import _get_model_manager, _get_ollama_client


# ─── Helpers ─────────────────────────────────────────────


def _owner_token(owner_id: str = "owner-abc-123") -> str:
    return create_access_token(subject=owner_id, role="owner")


def _auth_header(owner_id: str = "owner-abc-123") -> dict[str, str]:
    return {"Authorization": f"Bearer {_owner_token(owner_id)}"}


def _create_owner(client: TestClient) -> str:
    """Create an owner via setup and return the owner_id."""
    resp = client.post(
        "/api/auth/setup",
        json={
            "name": "Model Test Owner",
            "email": "modeltest@example.com",
            "preferred_language": "en",
            "secret_word": "testsecret",
        },
    )
    assert resp.status_code == 201
    return resp.json()["owner_id"]


# ─── GET /api/model/status ───────────────────────────────


def test_model_status_ollama_ok(client: TestClient) -> None:
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(
        return_value={"status": "ok", "ollama_response": "Ollama is running"}
    )
    mock_client.list_models = AsyncMock(
        return_value=[{"name": "mistral:7b-instruct", "size": 4_000_000_000}]
    )

    from app.main import app

    app.dependency_overrides[_get_ollama_client] = lambda: mock_client

    resp = client.get("/api/model/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_status"] == "ok"
    assert data["ollama_detail"] == "Ollama is running"
    assert len(data["models"]) == 1
    assert data["models"][0]["name"] == "mistral:7b-instruct"

    app.dependency_overrides.pop(_get_ollama_client, None)


def test_model_status_ollama_unreachable(client: TestClient) -> None:
    mock_client = AsyncMock()
    mock_client.health_check = AsyncMock(
        return_value={"status": "unreachable", "error": "Cannot connect to Ollama"}
    )

    from app.main import app

    app.dependency_overrides[_get_ollama_client] = lambda: mock_client

    resp = client.get("/api/model/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ollama_status"] == "unreachable"
    assert data["ollama_detail"] == "Cannot connect to Ollama"
    assert data["models"] == []

    app.dependency_overrides.pop(_get_ollama_client, None)


# ─── POST /api/model/initialize ──────────────────────────


def test_model_initialize_success(client: TestClient) -> None:
    owner_id = _create_owner(client)

    async def fake_ensure_base_model() -> list[dict]:
        return [{"status": "already_available", "model": "mistral:7b-instruct"}]

    async def fake_create_owner_model(oid: str, db: object) -> dict:
        return {
            "model_name": f"replica-{oid[:12]}",
            "owner_id": oid,
            "system_prompt": "You are the personal AI replica of Model Test Owner.",
            "progress": [{"status": "success"}],
        }

    mock_manager = AsyncMock()
    mock_manager.ensure_base_model = fake_ensure_base_model
    mock_manager.create_owner_model = fake_create_owner_model

    from app.main import app

    app.dependency_overrides[_get_model_manager] = lambda: mock_manager

    resp = client.post(
        "/api/model/initialize",
        json={"owner_id": owner_id},
        headers=_auth_header(owner_id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["base_model_status"] == "already_available"
    assert data["owner_model"]["model_name"].startswith("replica-")
    assert data["owner_model"]["owner_id"] == owner_id

    app.dependency_overrides.pop(_get_model_manager, None)


def test_model_initialize_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/model/initialize",
        json={"owner_id": "some-id"},
    )
    assert resp.status_code == 401


def test_model_initialize_rejects_other_owner(client: TestClient) -> None:
    owner_id = _create_owner(client)

    resp = client.post(
        "/api/model/initialize",
        json={"owner_id": owner_id},
        headers=_auth_header("different-owner-id"),
    )
    assert resp.status_code == 403
    assert "only initialize your own model" in resp.json()["detail"].lower()


# ─── GET /api/model/info ─────────────────────────────────


def test_model_info_exists(client: TestClient) -> None:
    owner_id = _create_owner(client)

    async def fake_get_model_info(oid: str) -> dict:
        return {
            "model_name": f"replica-{oid[:12]}",
            "parameters": "7B",
        }

    mock_manager = AsyncMock()
    mock_manager.get_model_info = fake_get_model_info

    from app.main import app

    app.dependency_overrides[_get_model_manager] = lambda: mock_manager

    resp = client.get("/api/model/info", headers=_auth_header(owner_id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["model_name"].startswith("replica-")
    assert data["details"] is not None

    app.dependency_overrides.pop(_get_model_manager, None)


def test_model_info_not_exists(client: TestClient) -> None:
    owner_id = _create_owner(client)

    mock_manager = AsyncMock()
    mock_manager.get_model_info = AsyncMock(return_value=None)

    from app.main import app

    app.dependency_overrides[_get_model_manager] = lambda: mock_manager

    resp = client.get("/api/model/info", headers=_auth_header(owner_id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is False
    assert data["model_name"] is None

    app.dependency_overrides.pop(_get_model_manager, None)


def test_model_info_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/model/info")
    assert resp.status_code == 401
