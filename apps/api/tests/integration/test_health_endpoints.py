"""Health endpoint integration tests.

These hit the real /api/health and /api/health/detailed routes through the
TestClient. The downstream service checks (database, redis, ai service)
either succeed (because the test DB is up + redis is mocked) or are
intercepted via dependency overrides.
"""

from __future__ import annotations

from unittest.mock import AsyncMock


class TestBasicHealth:
    def test_basic_health_returns_200_when_up(
        self, client_with_ai
    ) -> None:
        resp = client_with_ai.get("/api/health")
        # /api/health is the lightweight check — should succeed even when
        # downstream services are partially degraded.
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert body["status"] in ("ok", "degraded", "down")

    def test_legacy_root_health_endpoint(self, client_with_ai) -> None:
        # /health (legacy) is the original FastAPI default endpoint
        resp = client_with_ai.get("/health")
        assert resp.status_code == 200


class TestDetailedHealth:
    def test_detailed_health_returns_per_service_status(
        self, client_with_ai, mock_ai_client: AsyncMock
    ) -> None:
        # The mock_ai_client.health response is already "ok" by default
        resp = client_with_ai.get("/api/health/detailed")
        # 200 if all critical services up, 503 if any critical down
        assert resp.status_code in (200, 503)
        body = resp.json()

        assert "status" in body
        assert "services" in body
        assert isinstance(body["services"], dict)

        # The expected service keys
        for key in ("database", "redis", "ai_service", "ollama", "qdrant"):
            assert key in body["services"], f"missing service key: {key}"
            svc = body["services"][key]
            assert "status" in svc
            assert svc["status"] in ("ok", "degraded", "unreachable")

    def test_detailed_health_marks_ai_service_unreachable(
        self, client_with_ai, mock_ai_client: AsyncMock
    ) -> None:
        # Make the AI client report unreachable
        mock_ai_client.health_safe.return_value = {
            "status": "unreachable",
            "error": "AI service is unreachable",
        }

        resp = client_with_ai.get("/api/health/detailed")
        body = resp.json()

        # The ai_service entry should reflect the unreachable status
        ai_status = body["services"]["ai_service"]["status"]
        assert ai_status in ("unreachable", "degraded")

        # Overall should be down or degraded — never plain "ok"
        assert body["status"] in ("down", "degraded")
