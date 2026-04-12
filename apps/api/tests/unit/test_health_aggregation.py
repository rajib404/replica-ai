"""Unit tests for the health aggregation logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.routers.health import (
    ServiceHealth,
    _check_ai_service,
    _check_database,
    _check_ollama,
    _check_qdrant,
    _check_redis,
    _compute_overall,
    _timed,
)


# ─── _compute_overall ───────────────────────────────────────


class TestComputeOverall:
    def test_all_ok_returns_ok(self) -> None:
        services = {
            "database": ServiceHealth(status="ok"),
            "redis": ServiceHealth(status="ok"),
            "ai_service": ServiceHealth(status="ok"),
            "ollama": ServiceHealth(status="ok"),
            "qdrant": ServiceHealth(status="ok"),
        }
        assert _compute_overall(services) == "ok"

    def test_critical_service_down_returns_down(self) -> None:
        services = {
            "database": ServiceHealth(status="unreachable"),
            "redis": ServiceHealth(status="ok"),
            "ai_service": ServiceHealth(status="ok"),
            "ollama": ServiceHealth(status="ok"),
            "qdrant": ServiceHealth(status="ok"),
        }
        assert _compute_overall(services) == "down"

    def test_ai_service_down_is_critical(self) -> None:
        services = {
            "database": ServiceHealth(status="ok"),
            "ai_service": ServiceHealth(status="unreachable"),
            "ollama": ServiceHealth(status="ok"),
            "redis": ServiceHealth(status="ok"),
            "qdrant": ServiceHealth(status="ok"),
        }
        assert _compute_overall(services) == "down"

    def test_ollama_down_is_critical(self) -> None:
        services = {
            "database": ServiceHealth(status="ok"),
            "ai_service": ServiceHealth(status="ok"),
            "ollama": ServiceHealth(status="unreachable"),
            "redis": ServiceHealth(status="ok"),
            "qdrant": ServiceHealth(status="ok"),
        }
        assert _compute_overall(services) == "down"

    def test_redis_down_is_degraded_not_down(self) -> None:
        services = {
            "database": ServiceHealth(status="ok"),
            "ai_service": ServiceHealth(status="ok"),
            "ollama": ServiceHealth(status="ok"),
            "redis": ServiceHealth(status="unreachable"),
            "qdrant": ServiceHealth(status="ok"),
        }
        assert _compute_overall(services) == "degraded"

    def test_qdrant_down_is_degraded_not_down(self) -> None:
        services = {
            "database": ServiceHealth(status="ok"),
            "ai_service": ServiceHealth(status="ok"),
            "ollama": ServiceHealth(status="ok"),
            "redis": ServiceHealth(status="ok"),
            "qdrant": ServiceHealth(status="unreachable"),
        }
        assert _compute_overall(services) == "degraded"

    def test_both_critical_and_noncritical_down_is_down(self) -> None:
        services = {
            "database": ServiceHealth(status="unreachable"),
            "redis": ServiceHealth(status="unreachable"),
            "ai_service": ServiceHealth(status="ok"),
            "ollama": ServiceHealth(status="ok"),
            "qdrant": ServiceHealth(status="ok"),
        }
        assert _compute_overall(services) == "down"

    def test_empty_services_returns_ok(self) -> None:
        assert _compute_overall({}) == "ok"


# ─── _timed ─────────────────────────────────────────────────


class TestTimed:
    async def test_wraps_success_with_latency(self) -> None:
        async def coro() -> ServiceHealth:
            return ServiceHealth(status="ok")

        result = await _timed(coro(), "test")
        assert result.status == "ok"
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    async def test_exception_becomes_unreachable(self) -> None:
        async def coro() -> ServiceHealth:
            raise RuntimeError("boom")

        result = await _timed(coro(), "test")
        assert result.status == "unreachable"
        assert "boom" in (result.message or "")

    async def test_timeout_becomes_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio

        from app.routers import health as mod

        monkeypatch.setattr(mod, "_CHECK_TIMEOUT_SEC", 0.05)

        async def slow() -> ServiceHealth:
            await asyncio.sleep(1.0)
            return ServiceHealth(status="ok")

        result = await _timed(slow(), "slow")
        assert result.status == "unreachable"
        assert "timed out" in (result.message or "").lower()


# ─── Individual checkers ────────────────────────────────────


class TestCheckDatabase:
    async def test_ok_when_scalar_returns(self) -> None:
        db = AsyncMock()

        class _Result:
            def scalar_one(self) -> int:
                return 1

        db.execute = AsyncMock(return_value=_Result())

        result = await _check_database(db)
        assert result.status == "ok"


class TestCheckRedis:
    async def test_ok_when_ping(self) -> None:
        r = AsyncMock()
        r.ping = AsyncMock(return_value=True)
        result = await _check_redis(r)
        assert result.status == "ok"

    async def test_unreachable_when_ping_false(self) -> None:
        r = AsyncMock()
        r.ping = AsyncMock(return_value=False)
        result = await _check_redis(r)
        assert result.status == "unreachable"


class TestCheckAiService:
    async def test_ok_passthrough(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(return_value={"status": "ok", "ollama": {"status": "ok"}})
        result = await _check_ai_service(ai)
        assert result.status == "ok"
        assert "ai service reachable" in (result.message or "")

    async def test_unreachable_when_unknown_status(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(return_value={"status": "broken"})
        result = await _check_ai_service(ai)
        assert result.status == "unreachable"

    async def test_degraded_forwarded(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(return_value={"status": "degraded"})
        result = await _check_ai_service(ai)
        assert result.status == "degraded"


class TestCheckOllama:
    async def test_ok_from_nested(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(return_value={"ollama": {"status": "ok"}})
        result = await _check_ollama(ai)
        assert result.status == "ok"

    async def test_unreachable_from_nested(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(
            return_value={"ollama": {"status": "down", "error": "no conn"}}
        )
        result = await _check_ollama(ai)
        assert result.status == "unreachable"
        assert "no conn" in (result.message or "")


class TestCheckQdrant:
    async def test_ok(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(return_value={"qdrant": {"status": "ok"}})
        result = await _check_qdrant(ai)
        assert result.status == "ok"

    async def test_unreachable_carries_rag_warning(self) -> None:
        ai = AsyncMock()
        ai.health = AsyncMock(return_value={"qdrant": {"status": "down"}})
        result = await _check_qdrant(ai)
        assert result.status == "unreachable"
        assert "without RAG" in (result.message or "")
