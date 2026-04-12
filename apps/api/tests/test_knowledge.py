import json
from io import BytesIO
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.knowledge import ContentType, KnowledgeEntry
from app.routers.knowledge import _get_ingestor


# ─── Helpers ─────────────────────────────────────────────


OWNER_ID = "owner-knowledge-123"


def _auth_header(owner_id: str = OWNER_ID) -> dict[str, str]:
    token = create_access_token(subject=owner_id, role="owner")
    return {"Authorization": f"Bearer {token}"}


def _mock_ingestor() -> AsyncMock:
    ingestor = AsyncMock()
    ingestor.ingest_text = AsyncMock(return_value="entry-uuid-001")
    ingestor.ingest_audio_background = AsyncMock()
    ingestor.ingest_video_background = AsyncMock()
    ingestor.ingest_document_background = AsyncMock()
    ingestor.list_entries = AsyncMock(return_value=([], 0))
    ingestor.get_entry = AsyncMock(return_value=None)
    ingestor.delete_entry = AsyncMock(return_value=False)
    return ingestor


def _override_ingestor(mock: AsyncMock) -> None:
    from app.main import app
    app.dependency_overrides[_get_ingestor] = lambda: mock


def _clear_override() -> None:
    from app.main import app
    app.dependency_overrides.pop(_get_ingestor, None)


# ─── POST /api/knowledge/text ───────────────────────────


def test_text_ingest_success(client: TestClient) -> None:
    mock = _mock_ingestor()
    _override_ingestor(mock)

    resp = client.post(
        "/api/knowledge/text",
        json={"text": "Hello, this is test knowledge."},
        headers=_auth_header(),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_id"] == "entry-uuid-001"
    assert data["status"] == "completed"
    mock.ingest_text.assert_called_once()

    _clear_override()


def test_text_ingest_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/knowledge/text",
        json={"text": "Some text"},
    )
    assert resp.status_code == 401


def test_text_ingest_empty_text(client: TestClient) -> None:
    resp = client.post(
        "/api/knowledge/text",
        json={"text": ""},
        headers=_auth_header(),
    )
    assert resp.status_code == 422


# ─── POST /api/knowledge/audio ──────────────────────────


def test_audio_ingest_accepted(client: TestClient, mock_redis: AsyncMock) -> None:
    mock = _mock_ingestor()
    _override_ingestor(mock)

    fake_audio = BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/knowledge/audio",
        files={"file": ("test.wav", fake_audio, "audio/wav")},
        headers=_auth_header(),
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"

    _clear_override()


def test_audio_ingest_rejects_bad_format(client: TestClient) -> None:
    mock = _mock_ingestor()
    _override_ingestor(mock)

    fake_file = BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/knowledge/audio",
        files={"file": ("test.exe", fake_file, "application/octet-stream")},
        headers=_auth_header(),
    )
    assert resp.status_code == 400
    assert "Unsupported audio format" in resp.json()["detail"]

    _clear_override()


# ─── POST /api/knowledge/document ───────────────────────


def test_document_ingest_accepted(client: TestClient, mock_redis: AsyncMock) -> None:
    mock = _mock_ingestor()
    _override_ingestor(mock)

    fake_doc = BytesIO(b"Some document content")
    resp = client.post(
        "/api/knowledge/document",
        files={"file": ("test.txt", fake_doc, "text/plain")},
        headers=_auth_header(),
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"

    _clear_override()


def test_document_ingest_rejects_bad_format(client: TestClient) -> None:
    mock = _mock_ingestor()
    _override_ingestor(mock)

    fake_file = BytesIO(b"\x00" * 100)
    resp = client.post(
        "/api/knowledge/document",
        files={"file": ("test.zip", fake_file, "application/zip")},
        headers=_auth_header(),
    )
    assert resp.status_code == 400
    assert "Unsupported document format" in resp.json()["detail"]

    _clear_override()


# ─── GET /api/knowledge/entries ──────────────────────────


def test_list_entries_empty(client: TestClient) -> None:
    mock = _mock_ingestor()
    _override_ingestor(mock)

    resp = client.get("/api/knowledge/entries", headers=_auth_header())
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["total"] == 0
    assert data["page"] == 1

    _clear_override()


def test_list_entries_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/knowledge/entries")
    assert resp.status_code == 401


# ─── GET /api/knowledge/tasks/{task_id} ─────────────────


def test_get_task_status(client: TestClient, mock_redis: AsyncMock) -> None:
    task_data = {
        "task_id": "task-abc",
        "owner_id": OWNER_ID,
        "status": "processing",
        "progress": 50,
        "result": None,
        "error": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:01:00",
    }
    mock_redis.get = AsyncMock(return_value=json.dumps(task_data))

    resp = client.get("/api/knowledge/tasks/task-abc", headers=_auth_header())
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task-abc"
    assert data["status"] == "processing"
    assert data["progress"] == 50


def test_get_task_not_found(client: TestClient, mock_redis: AsyncMock) -> None:
    mock_redis.get = AsyncMock(return_value=None)

    resp = client.get("/api/knowledge/tasks/nonexistent", headers=_auth_header())
    assert resp.status_code == 404


# ─── DELETE /api/knowledge/entries/{entry_id} ────────────


def test_delete_entry_success(client: TestClient) -> None:
    mock = _mock_ingestor()
    mock.delete_entry = AsyncMock(return_value=True)
    _override_ingestor(mock)

    resp = client.delete(
        "/api/knowledge/entries/entry-uuid-001",
        headers=_auth_header(),
    )
    assert resp.status_code == 204
    mock.delete_entry.assert_called_once()

    _clear_override()


def test_delete_entry_not_found(client: TestClient) -> None:
    mock = _mock_ingestor()
    mock.delete_entry = AsyncMock(return_value=False)
    _override_ingestor(mock)

    resp = client.delete(
        "/api/knowledge/entries/nonexistent",
        headers=_auth_header(),
    )
    assert resp.status_code == 404

    _clear_override()
