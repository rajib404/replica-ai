from redis.asyncio import Redis

from app.core.config import settings

VERIFY_PREFIX = "rate:verify:"
LOCKOUT_PREFIX = "rate:lockout:"


async def check_rate_limit(redis: Redis, owner_id: str) -> tuple[bool, int]:
    """Check if owner is rate-limited for verification attempts.

    Returns (allowed, seconds_remaining).
    - allowed=True, 0  → proceed
    - allowed=False, N → locked out for N more seconds
    """
    lockout_key = f"{LOCKOUT_PREFIX}{owner_id}"
    lockout_ttl = await redis.ttl(lockout_key)
    if lockout_ttl > 0:
        return False, lockout_ttl

    attempts_key = f"{VERIFY_PREFIX}{owner_id}"
    attempts = await redis.get(attempts_key)
    current = int(attempts) if attempts else 0

    if current >= settings.verify_max_attempts:
        await redis.setex(lockout_key, settings.verify_lockout_seconds, "1")
        await redis.delete(attempts_key)
        return False, settings.verify_lockout_seconds

    return True, 0


async def record_attempt(redis: Redis, owner_id: str) -> int:
    """Record a failed verification attempt. Returns new count."""
    key = f"{VERIFY_PREFIX}{owner_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.verify_window_seconds)
    return count


async def clear_attempts(redis: Redis, owner_id: str) -> None:
    """Clear attempt counter on successful verification."""
    await redis.delete(f"{VERIFY_PREFIX}{owner_id}")
    await redis.delete(f"{LOCKOUT_PREFIX}{owner_id}")
