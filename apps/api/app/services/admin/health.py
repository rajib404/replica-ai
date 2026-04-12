"""Service health probes for the admin dashboard."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import get_ai_client
from app.core.config import settings


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


async def check_postgres(db: AsyncSession) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        return {
            "name": "postgres",
            "status": "healthy",
            "response_time_ms": _ms(start),
            "last_error": None,
            "checked_at": _now(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "postgres",
            "status": "down",
            "response_time_ms": _ms(start),
            "last_error": str(exc),
            "checked_at": _now(),
        }


async def check_redis() -> dict[str, Any]:
    start = time.perf_counter()
    client: aioredis.Redis | None = None
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        return {
            "name": "redis",
            "status": "healthy",
            "response_time_ms": _ms(start),
            "last_error": None,
            "checked_at": _now(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "redis",
            "status": "down",
            "response_time_ms": _ms(start),
            "last_error": str(exc),
            "checked_at": _now(),
        }
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


async def check_ai_service() -> dict[str, Any]:
    start = time.perf_counter()
    snapshot = await get_ai_client().health_safe()
    elapsed = _ms(start)
    status_value = snapshot.get("status", "unknown")
    if status_value in ("healthy", "ok"):
        return {
            "name": "ai_service",
            "status": "healthy",
            "response_time_ms": elapsed,
            "last_error": None,
            "checked_at": _now(),
            "details": snapshot,
        }
    return {
        "name": "ai_service",
        "status": "down" if status_value in ("unreachable", "error", "timeout") else "degraded",
        "response_time_ms": elapsed,
        "last_error": snapshot.get("error"),
        "checked_at": _now(),
        "details": snapshot,
    }


def _extract_subservice(snapshot: dict[str, Any], key: str) -> tuple[str, str | None]:
    """Pull a sub-service status out of the AI service health response."""
    sub = snapshot.get(key)
    if isinstance(sub, dict):
        status = sub.get("status", "unknown")
        if status in ("healthy", "ok", "ready"):
            return "healthy", None
        return ("down" if status in ("unreachable", "error", "down") else "degraded"), sub.get(
            "error"
        )
    if isinstance(sub, str):
        return ("healthy", None) if sub in ("healthy", "ok", "ready") else ("degraded", sub)
    return "unknown", None


async def collect_health_snapshot(db: AsyncSession) -> list[dict[str, Any]]:
    """Run all probes in parallel and return one entry per service."""
    pg_task = asyncio.create_task(check_postgres(db))
    redis_task = asyncio.create_task(check_redis())
    ai_task = asyncio.create_task(check_ai_service())

    pg, redis_entry, ai_entry = await asyncio.gather(
        pg_task, redis_task, ai_task, return_exceptions=False
    )

    entries: list[dict[str, Any]] = [pg, redis_entry, ai_entry]

    ai_details = ai_entry.get("details") if isinstance(ai_entry, dict) else None
    if isinstance(ai_details, dict):
        for sub_name in ("qdrant", "ollama"):
            sub_status, sub_error = _extract_subservice(ai_details, sub_name)
            entries.append(
                {
                    "name": sub_name,
                    "status": sub_status,
                    "response_time_ms": None,
                    "last_error": sub_error,
                    "checked_at": _now(),
                }
            )
    return entries
