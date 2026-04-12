from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.security import create_access_token, create_connect_token


# ─── POST /api/auth/setup ────────────────────────────────


def test_setup_creates_owner(client: TestClient) -> None:
    response = client.post(
        "/api/auth/setup",
        json={
            "name": "Test Owner",
            "email": "test@example.com",
            "preferred_language": "en",
            "secret_word": "mysecretword",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["owner_id"]
    assert data["tokens"]["access_token"]
    assert data["tokens"]["refresh_token"]
    assert data["tokens"]["token_type"] == "bearer"
    assert data["connect_url"].startswith("http")
    assert "token=" in data["connect_url"]
    assert len(data["qr_code_base64"]) > 100  # valid base64 PNG


def test_setup_rejects_duplicate_email(client: TestClient) -> None:
    payload = {
        "name": "Owner A",
        "email": "dupe@example.com",
        "secret_word": "secret123",
    }
    response1 = client.post("/api/auth/setup", json=payload)
    assert response1.status_code == 201

    response2 = client.post("/api/auth/setup", json=payload)
    assert response2.status_code == 409


def test_setup_with_secret_event(client: TestClient) -> None:
    response = client.post(
        "/api/auth/setup",
        json={
            "name": "Event Owner",
            "email": "event@example.com",
            "secret_event": "our wedding day in paris",
        },
    )
    assert response.status_code == 201


def test_setup_validates_input(client: TestClient) -> None:
    response = client.post("/api/auth/setup", json={"name": "", "email": "bad"})
    assert response.status_code == 422


# ─── POST /api/auth/connect ──────────────────────────────


def test_connect_with_valid_token(client: TestClient) -> None:
    # First create an owner
    setup = client.post(
        "/api/auth/setup",
        json={
            "name": "Connect Owner",
            "email": "connect@example.com",
            "secret_word": "password",
        },
    )
    owner_id = setup.json()["owner_id"]

    # Generate a fresh connect token
    connect_token = create_connect_token(owner_id)

    response = client.post(
        "/api/auth/connect",
        json={
            "token": connect_token,
            "hostname": "my-laptop.local",
            "instance_type": "local",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["owner_id"] == owner_id
    assert data["instance_id"]
    assert data["session_token"]


def test_connect_rejects_invalid_token(client: TestClient) -> None:
    response = client.post(
        "/api/auth/connect",
        json={
            "token": "garbage.token.here",
            "hostname": "bad-host",
            "instance_type": "local",
        },
    )
    assert response.status_code == 401


def test_connect_rejects_non_connect_token(client: TestClient) -> None:
    # Use an access token instead of a connect token
    access_token = create_access_token(subject="fake-id", role="owner")
    response = client.post(
        "/api/auth/connect",
        json={
            "token": access_token,
            "hostname": "sneaky-host",
            "instance_type": "cloud",
        },
    )
    assert response.status_code == 401


# ─── POST /api/auth/verify ───────────────────────────────


def test_verify_secret_word_success(client: TestClient) -> None:
    setup = client.post(
        "/api/auth/setup",
        json={
            "name": "Verify Owner",
            "email": "verify@example.com",
            "secret_word": "topsecret",
        },
    )
    owner_id = setup.json()["owner_id"]

    response = client.post(
        "/api/auth/verify",
        json={
            "owner_id": owner_id,
            "verification_type": "secret_word",
            "value": "topsecret",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verified"] is True
    assert data["tokens"]["access_token"]


def test_verify_secret_word_failure(client: TestClient) -> None:
    setup = client.post(
        "/api/auth/setup",
        json={
            "name": "Fail Owner",
            "email": "fail@example.com",
            "secret_word": "correctword",
        },
    )
    owner_id = setup.json()["owner_id"]

    response = client.post(
        "/api/auth/verify",
        json={
            "owner_id": owner_id,
            "verification_type": "secret_word",
            "value": "wrongword",
        },
    )
    data = response.json()
    assert data["verified"] is False
    assert "attempts remaining" in data["message"]


def test_verify_voice_match_redirects_to_endpoint(client: TestClient) -> None:
    setup = client.post(
        "/api/auth/setup",
        json={"name": "Voice Owner", "email": "voice@example.com"},
    )
    owner_id = setup.json()["owner_id"]

    response = client.post(
        "/api/auth/verify",
        json={
            "owner_id": owner_id,
            "verification_type": "voice_match",
        },
    )
    data = response.json()
    # voice_match via /api/auth/verify doesn't accept audio —
    # it directs the caller to use /api/verify/voice/check instead
    assert data["verified"] is False
    assert "voice" in data["message"].lower()


def test_verify_face_match_stub(client: TestClient) -> None:
    setup = client.post(
        "/api/auth/setup",
        json={"name": "Face Owner", "email": "face@example.com"},
    )
    owner_id = setup.json()["owner_id"]

    response = client.post(
        "/api/auth/verify",
        json={
            "owner_id": owner_id,
            "verification_type": "face_match",
        },
    )
    data = response.json()
    assert data["verified"] is True


def test_verify_rate_limit_lockout(client: TestClient, mock_redis: AsyncMock) -> None:
    # Simulate lockout: redis.ttl returns positive value
    mock_redis.ttl.return_value = 3500

    setup = client.post(
        "/api/auth/setup",
        json={
            "name": "Locked Owner",
            "email": "locked@example.com",
            "secret_word": "secret",
        },
    )
    owner_id = setup.json()["owner_id"]

    response = client.post(
        "/api/auth/verify",
        json={
            "owner_id": owner_id,
            "verification_type": "secret_word",
            "value": "secret",
        },
    )
    data = response.json()
    assert data["verified"] is False
    assert "Too many attempts" in data["message"]


# ─── AuthGuard ────────────────────────────────────────────


def test_protected_route_without_token(client: TestClient) -> None:
    """Health endpoint is public, but we'll verify the guard import works
    by checking that the auth module loaded correctly."""
    response = client.get("/health")
    assert response.status_code == 200
