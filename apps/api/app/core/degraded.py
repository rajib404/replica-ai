"""Graceful-degradation helpers.

The goal is to keep the chat experience functional when non-critical
dependencies are unavailable:

- **Qdrant down** → chat still works, just without RAG context. The
  caller falls back to ``ai.generate`` and the response is tagged with
  ``degraded: true`` and a user-visible warning.
- **Redis down** → no caching, context is loaded fresh every time. We
  treat the Redis client as optional and swallow connection errors in
  helper wrappers.
- **External LLM down** → surface a friendly message to the user and
  suggest falling back to the local model.

These helpers are intentionally permissive: they log the failure and
return a fallback value instead of raising.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.ai_client import AIServiceClient
from app.core.config import settings
from app.core.exceptions import ModelUnavailableError

logger = logging.getLogger("replica.degraded")

DEGRADED_RAG_WARNING = (
    "Knowledge search is temporarily unavailable. "
    "I can still chat, but I won't be able to recall details from your saved knowledge."
)


# ─── Redis helpers ───────────────────────────────────────────


async def safe_redis_get(r: aioredis.Redis | None, key: str) -> str | None:
    """GET a key, swallowing connection errors when ``cache_optional`` is on."""
    if r is None:
        return None
    try:
        value = await r.get(key)
        return value if isinstance(value, str) or value is None else str(value)
    except (RedisConnectionError, RedisTimeoutError) as e:
        if settings.cache_optional:
            logger.warning("Redis unavailable for GET %s: %s — continuing without cache", key, e)
            return None
        raise


async def safe_redis_set(
    r: aioredis.Redis | None,
    key: str,
    value: str,
    ex: int | None = None,
) -> bool:
    """SET a key, swallowing connection errors when ``cache_optional`` is on."""
    if r is None:
        return False
    try:
        await r.set(key, value, ex=ex)
        return True
    except (RedisConnectionError, RedisTimeoutError) as e:
        if settings.cache_optional:
            logger.warning("Redis unavailable for SET %s: %s — skipping cache write", key, e)
            return False
        raise


# ─── RAG fallback ───────────────────────────────────────────


async def rag_generate_with_fallback(
    *,
    ai: AIServiceClient,
    owner_id: str,
    message: str,
    conversation_history: list[dict[str, str]],
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Try ``ai.rag_generate`` first, fall back to ``ai.generate`` without RAG.

    Returns a dict with at least::

        {"response": "...", "sources": [...], "degraded": bool, "warning": str | None}

    If Ollama itself is down, raises ``ModelUnavailableError`` so the
    global handler produces a consistent 503.
    """
    try:
        result = await ai.rag_generate(
            owner_id=owner_id,
            message=message,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
            model=model,
        )
        return {
            "response": result.get("response", ""),
            "sources": result.get("sources", []),
            "degraded": False,
            "warning": None,
        }
    except ModelUnavailableError:
        # Ollama itself is down — no fallback possible.
        raise
    except (httpx.HTTPStatusError, httpx.HTTPError) as e:
        if not settings.rag_optional:
            raise
        logger.warning("RAG unavailable (%s) — falling back to plain generation", e)

    # Fallback: plain generate using conversation history as prompt context.
    degraded_prompt = _render_chat_prompt(message, conversation_history)
    try:
        result = await ai.generate(
            prompt=degraded_prompt,
            model=model,
            system_prompt=system_prompt,
        )
        return {
            "response": result.get("response", ""),
            "sources": [],
            "degraded": True,
            "warning": DEGRADED_RAG_WARNING,
        }
    except Exception as e:  # noqa: BLE001
        # Even the plain fallback failed — raise the clean 503.
        logger.exception("Fallback generation failed")
        raise ModelUnavailableError() from e


def _render_chat_prompt(
    message: str,
    conversation_history: list[dict[str, str]],
) -> str:
    """Render conversation history + new message as a single prompt string.

    Used when RAG is unavailable and we need to call plain ``ai.generate``.
    """
    parts: list[str] = []
    for turn in conversation_history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        prefix = "User" if role == "user" else "Assistant"
        parts.append(f"{prefix}: {content}")
    parts.append(f"User: {message}")
    parts.append("Assistant:")
    return "\n".join(parts)


__all__ = [
    "DEGRADED_RAG_WARNING",
    "safe_redis_get",
    "safe_redis_set",
    "rag_generate_with_fallback",
]
