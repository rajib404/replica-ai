"""Unit tests for the verification rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core import rate_limit
from app.core.rate_limit import (
    LOCKOUT_PREFIX,
    VERIFY_PREFIX,
    check_rate_limit,
    clear_attempts,
    record_attempt,
)


@pytest.fixture
def fake_redis() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.ttl = AsyncMock(return_value=-2)  # no key
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    return r


class TestCheckRateLimit:
    async def test_allowed_when_no_attempts(self, fake_redis: AsyncMock) -> None:
        allowed, remaining = await check_rate_limit(fake_redis, "owner_1")
        assert allowed is True
        assert remaining == 0

    async def test_allowed_when_under_limit(self, fake_redis: AsyncMock) -> None:
        fake_redis.get = AsyncMock(return_value="2")
        allowed, _ = await check_rate_limit(fake_redis, "owner_1")
        assert allowed is True

    async def test_locked_out_when_at_limit(
        self, fake_redis: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rate_limit.settings, "verify_max_attempts", 3)
        monkeypatch.setattr(rate_limit.settings, "verify_lockout_seconds", 3600)
        fake_redis.get = AsyncMock(return_value="3")

        allowed, remaining = await check_rate_limit(fake_redis, "owner_1")
        assert allowed is False
        assert remaining == 3600
        fake_redis.setex.assert_awaited_once()
        fake_redis.delete.assert_awaited_once()

    async def test_locked_out_when_over_limit(
        self, fake_redis: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rate_limit.settings, "verify_max_attempts", 3)
        fake_redis.get = AsyncMock(return_value="99")
        allowed, _ = await check_rate_limit(fake_redis, "owner_1")
        assert allowed is False

    async def test_existing_lockout_blocks_check(
        self, fake_redis: AsyncMock
    ) -> None:
        fake_redis.ttl = AsyncMock(return_value=1200)  # 20 min lockout remaining
        allowed, remaining = await check_rate_limit(fake_redis, "owner_1")
        assert allowed is False
        assert remaining == 1200
        # Should short-circuit — never check attempts key
        fake_redis.get.assert_not_called()


class TestRecordAttempt:
    async def test_first_attempt_sets_expiry(
        self, fake_redis: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rate_limit.settings, "verify_window_seconds", 900)
        fake_redis.incr = AsyncMock(return_value=1)

        count = await record_attempt(fake_redis, "owner_1")
        assert count == 1
        fake_redis.expire.assert_awaited_once()
        args = fake_redis.expire.await_args
        assert args.args[0] == f"{VERIFY_PREFIX}owner_1"
        assert args.args[1] == 900

    async def test_subsequent_attempt_does_not_reset_expiry(
        self, fake_redis: AsyncMock
    ) -> None:
        fake_redis.incr = AsyncMock(return_value=2)
        count = await record_attempt(fake_redis, "owner_1")
        assert count == 2
        fake_redis.expire.assert_not_called()


class TestClearAttempts:
    async def test_clears_both_keys(self, fake_redis: AsyncMock) -> None:
        await clear_attempts(fake_redis, "owner_1")
        # Should have deleted the attempts key AND the lockout key
        assert fake_redis.delete.await_count == 2
        calls = [c.args[0] for c in fake_redis.delete.await_args_list]
        assert f"{VERIFY_PREFIX}owner_1" in calls
        assert f"{LOCKOUT_PREFIX}owner_1" in calls
