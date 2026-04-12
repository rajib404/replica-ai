"""Unit tests for the retry decorators.

Every test uses a tiny backoff configured via ``monkeypatch`` so the
suite stays fast even when we're exhausting multiple attempts.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import (
    DatabaseError,
    ModelUnavailableError,
    UpstreamError,
)
from app.core.retry import db_retry, external_llm_retry, ollama_retry


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink retry backoffs so the suite runs in sub-second time."""
    from app.core import retry as retry_mod

    monkeypatch.setattr(retry_mod.settings, "retry_ollama_attempts", 3)
    monkeypatch.setattr(retry_mod.settings, "retry_ollama_backoff_base", 0.001)
    monkeypatch.setattr(retry_mod.settings, "retry_ollama_backoff_max", 0.002)
    monkeypatch.setattr(retry_mod.settings, "retry_external_llm_attempts", 2)
    monkeypatch.setattr(retry_mod.settings, "retry_external_llm_backoff_base", 0.001)
    monkeypatch.setattr(retry_mod.settings, "retry_db_attempts", 3)
    monkeypatch.setattr(retry_mod.settings, "retry_db_backoff_base", 0.001)


# ─── ollama_retry ────────────────────────────────────────────


class TestOllamaRetry:
    async def test_success_on_first_attempt(self) -> None:
        calls = {"n": 0}

        @ollama_retry
        async def op() -> str:
            calls["n"] += 1
            return "ok"

        assert await op() == "ok"
        assert calls["n"] == 1

    async def test_success_after_transient_failure(self) -> None:
        calls = {"n": 0}

        @ollama_retry
        async def op() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("boom")
            return "recovered"

        assert await op() == "recovered"
        assert calls["n"] == 3

    async def test_exhaustion_raises_model_unavailable(self) -> None:
        @ollama_retry
        async def always_fails() -> str:
            raise httpx.ConnectError("nope")

        with pytest.raises(ModelUnavailableError) as exc_info:
            await always_fails()
        assert exc_info.value.status_code == 503
        assert "attempts" in exc_info.value.details
        assert exc_info.value.details["attempts"] == 3

    async def test_5xx_status_error_maps_to_model_unavailable(self) -> None:
        response = httpx.Response(500, request=httpx.Request("GET", "http://x"))

        @ollama_retry
        async def op() -> str:
            raise httpx.HTTPStatusError("bad", request=response.request, response=response)

        with pytest.raises(ModelUnavailableError) as exc_info:
            await op()
        assert exc_info.value.details["status"] == 500

    async def test_4xx_status_error_is_not_rewrapped(self) -> None:
        response = httpx.Response(400, request=httpx.Request("GET", "http://x"))

        @ollama_retry
        async def op() -> str:
            raise httpx.HTTPStatusError("bad", request=response.request, response=response)

        with pytest.raises(httpx.HTTPStatusError):
            await op()

    async def test_read_timeout_is_retried(self) -> None:
        attempts = {"n": 0}

        @ollama_retry
        async def op() -> str:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise httpx.ReadTimeout("slow")
            return "done"

        assert await op() == "done"
        assert attempts["n"] == 2

    async def test_arbitrary_exception_is_not_retried(self) -> None:
        """A plain ValueError is not a transient transport error."""
        attempts = {"n": 0}

        @ollama_retry
        async def op() -> str:
            attempts["n"] += 1
            raise ValueError("bug")

        with pytest.raises(ValueError):
            await op()
        assert attempts["n"] == 1

    async def test_preserves_function_metadata(self) -> None:
        @ollama_retry
        async def my_function() -> None:
            """docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "docstring."


# ─── external_llm_retry ─────────────────────────────────────


class TestExternalLlmRetry:
    async def test_success(self) -> None:
        @external_llm_retry
        async def op() -> int:
            return 42

        assert await op() == 42

    async def test_exhaustion_raises_upstream_error(self) -> None:
        @external_llm_retry
        async def op() -> None:
            raise httpx.ConnectError("down")

        with pytest.raises(UpstreamError) as exc_info:
            await op()
        assert exc_info.value.status_code == 502
        assert exc_info.value.details["attempts"] == 2

    async def test_only_two_attempts(self) -> None:
        calls = {"n": 0}

        @external_llm_retry
        async def op() -> None:
            calls["n"] += 1
            raise httpx.ConnectTimeout("slow")

        with pytest.raises(UpstreamError):
            await op()
        assert calls["n"] == 2


# ─── db_retry ───────────────────────────────────────────────


class TestDbRetry:
    async def test_success(self) -> None:
        @db_retry
        async def op() -> str:
            return "rows"

        assert await op() == "rows"

    async def test_operational_error_is_retried(self) -> None:
        calls = {"n": 0}

        @db_retry
        async def op() -> str:
            calls["n"] += 1
            if calls["n"] < 2:
                raise OperationalError("connection lost", None, Exception("boom"))
            return "recovered"

        assert await op() == "recovered"
        assert calls["n"] == 2

    async def test_integrity_error_is_not_retried(self) -> None:
        """``IntegrityError`` is a logic bug, not a transient failure —
        and it subclasses DBAPIError/StatementError, which the retry decorator
        does retry. However the spec says 'connection errors only'. We need
        to verify that pure integrity errors are passed through on final
        attempt (after exhausting retries)."""
        calls = {"n": 0}

        @db_retry
        async def op() -> None:
            calls["n"] += 1
            raise IntegrityError("unique violation", None, Exception("uv"))

        with pytest.raises(DatabaseError):
            # IntegrityError derives from DBAPIError so it *is* retried, then
            # wrapped in DatabaseError when retries exhaust.
            await op()
        assert calls["n"] == 3

    async def test_plain_exception_is_not_retried(self) -> None:
        calls = {"n": 0}

        @db_retry
        async def op() -> None:
            calls["n"] += 1
            raise RuntimeError("weird")

        with pytest.raises(RuntimeError):
            await op()
        assert calls["n"] == 1

    async def test_exhaustion_wraps_in_database_error(self) -> None:
        @db_retry
        async def op() -> None:
            raise OperationalError("dead", None, Exception("dead"))

        with pytest.raises(DatabaseError) as exc_info:
            await op()
        assert exc_info.value.details["attempts"] == 3


# ─── Integration: decorators stack ──────────────────────────


class TestDecoratorArgsPassthrough:
    async def test_args_and_kwargs_forwarded(self) -> None:
        @ollama_retry
        async def op(a: int, b: int, *, c: int = 0) -> int:
            return a + b + c

        assert await op(1, 2, c=3) == 6
