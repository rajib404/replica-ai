"""Unit tests for graceful-degradation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.degraded import (
    DEGRADED_RAG_WARNING,
    _render_chat_prompt,
    rag_generate_with_fallback,
    safe_redis_get,
    safe_redis_set,
)
from app.core.exceptions import ModelUnavailableError


# ─── safe_redis_get / set ──────────────────────────────────


class TestSafeRedisGet:
    async def test_none_client_returns_none(self) -> None:
        assert await safe_redis_get(None, "k") is None

    async def test_returns_stored_value(self) -> None:
        r = AsyncMock()
        r.get = AsyncMock(return_value="cached")
        assert await safe_redis_get(r, "k") == "cached"

    async def test_swallows_connection_error_when_optional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "cache_optional", True)
        r = AsyncMock()
        r.get = AsyncMock(side_effect=RedisConnectionError("down"))
        assert await safe_redis_get(r, "k") is None

    async def test_reraises_when_not_optional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "cache_optional", False)
        r = AsyncMock()
        r.get = AsyncMock(side_effect=RedisConnectionError("down"))
        with pytest.raises(RedisConnectionError):
            await safe_redis_get(r, "k")

    async def test_swallows_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "cache_optional", True)
        r = AsyncMock()
        r.get = AsyncMock(side_effect=RedisTimeoutError("slow"))
        assert await safe_redis_get(r, "k") is None


class TestSafeRedisSet:
    async def test_none_client_returns_false(self) -> None:
        assert await safe_redis_set(None, "k", "v") is False

    async def test_successful_set(self) -> None:
        r = AsyncMock()
        r.set = AsyncMock()
        assert await safe_redis_set(r, "k", "v", ex=60) is True
        r.set.assert_awaited_once_with("k", "v", ex=60)

    async def test_swallows_connection_error_when_optional(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "cache_optional", True)
        r = AsyncMock()
        r.set = AsyncMock(side_effect=RedisConnectionError("down"))
        assert await safe_redis_set(r, "k", "v") is False


# ─── rag_generate_with_fallback ─────────────────────────────


class TestRagGenerateWithFallback:
    async def test_happy_path_not_degraded(self) -> None:
        ai = AsyncMock()
        ai.rag_generate = AsyncMock(
            return_value={"response": "hi!", "sources": [{"id": "k1"}]}
        )

        result = await rag_generate_with_fallback(
            ai=ai,
            owner_id="o1",
            message="hello",
            conversation_history=[],
        )
        assert result["response"] == "hi!"
        assert result["sources"] == [{"id": "k1"}]
        assert result["degraded"] is False
        assert result["warning"] is None
        ai.rag_generate.assert_awaited_once()
        ai.generate.assert_not_called() if hasattr(ai, "generate") else None

    async def test_falls_back_on_rag_http_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "rag_optional", True)

        ai = AsyncMock()
        ai.rag_generate = AsyncMock(
            side_effect=httpx.ConnectError("qdrant down")
        )
        ai.generate = AsyncMock(return_value={"response": "plain response"})

        result = await rag_generate_with_fallback(
            ai=ai,
            owner_id="o1",
            message="hi",
            conversation_history=[{"role": "user", "content": "earlier"}],
        )
        assert result["response"] == "plain response"
        assert result["sources"] == []
        assert result["degraded"] is True
        assert result["warning"] == DEGRADED_RAG_WARNING
        ai.generate.assert_awaited_once()

    async def test_model_unavailable_is_re_raised(self) -> None:
        """When Ollama itself is down, there's no fallback and we re-raise."""
        ai = AsyncMock()
        ai.rag_generate = AsyncMock(
            side_effect=ModelUnavailableError("ollama down")
        )
        ai.generate = AsyncMock()

        with pytest.raises(ModelUnavailableError):
            await rag_generate_with_fallback(
                ai=ai,
                owner_id="o1",
                message="hi",
                conversation_history=[],
            )
        ai.generate.assert_not_called()

    async def test_fallback_also_fails_raises_model_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "rag_optional", True)

        ai = AsyncMock()
        ai.rag_generate = AsyncMock(side_effect=httpx.ConnectError("x"))
        ai.generate = AsyncMock(side_effect=RuntimeError("also dead"))

        with pytest.raises(ModelUnavailableError):
            await rag_generate_with_fallback(
                ai=ai,
                owner_id="o1",
                message="hi",
                conversation_history=[],
            )

    async def test_respects_rag_optional_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core import degraded as mod

        monkeypatch.setattr(mod.settings, "rag_optional", False)

        ai = AsyncMock()
        ai.rag_generate = AsyncMock(side_effect=httpx.ConnectError("x"))

        with pytest.raises(httpx.ConnectError):
            await rag_generate_with_fallback(
                ai=ai,
                owner_id="o1",
                message="hi",
                conversation_history=[],
            )


# ─── _render_chat_prompt ────────────────────────────────────


class TestRenderChatPrompt:
    def test_empty_history_just_uses_message(self) -> None:
        prompt = _render_chat_prompt("hello", [])
        assert "User: hello" in prompt
        assert prompt.endswith("Assistant:")

    def test_includes_conversation_turns(self) -> None:
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
        ]
        prompt = _render_chat_prompt("second", history)
        assert "User: first" in prompt
        assert "Assistant: reply" in prompt
        assert "User: second" in prompt

    def test_limits_to_last_10_turns(self) -> None:
        history = [
            {"role": "user", "content": f"msg{i}"} for i in range(20)
        ]
        prompt = _render_chat_prompt("now", history)
        assert "msg19" in prompt
        assert "msg10" in prompt
        assert "msg9" not in prompt  # trimmed
        assert "msg0" not in prompt

    def test_unknown_role_treated_as_assistant(self) -> None:
        history = [{"role": "system", "content": "sys"}]
        prompt = _render_chat_prompt("msg", history)
        assert "Assistant: sys" in prompt
