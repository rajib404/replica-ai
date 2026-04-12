"""Health and status endpoints.

Two endpoints:

- ``GET /api/health`` — quick status suitable for load balancers and the
  footer status pill. Returns overall ``ok``/``degraded``/``down`` plus
  a per-service map. Never raises (always returns JSON).
- ``GET /api/health/detailed`` — verbose metrics (response times, disk
  usage, queue sizes) for the admin dashboard. Never raises.

Both endpoints execute checks concurrently with a short per-check
timeout so a single hung dependency can't stall the whole response.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.database import get_db
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Per-check hard timeout so one slow service can't stall the whole endpoint.
_CHECK_TIMEOUT_SEC = 2.0


class ServiceHealth(BaseModel):
    """Status of a single dependency."""

    status: str = Field(..., description="ok | degraded | unreachable")
    latency_ms: float | None = Field(None, description="Round-trip latency in milliseconds")
    message: str | None = Field(None, description="Human-readable detail or error")
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Quick health snapshot returned by ``GET /api/health``."""

    status: str = Field(..., description="Overall status: ok | degraded | down")
    version: str
    timestamp: str
    services: dict[str, ServiceHealth]


class DetailedHealthResponse(HealthResponse):
    """Extended metrics returned by ``GET /api/health/detailed``."""

    uptime_seconds: float
    process_id: int
    disk: dict[str, Any]
    queues: dict[str, Any]


# ─── Check helpers ───────────────────────────────────────────


async def _timed(coro: Any, name: str) -> ServiceHealth:
    """Run a health check with timeout, convert exceptions to degraded status."""
    start = time.perf_counter()
    try:
        result: ServiceHealth = await asyncio.wait_for(coro, timeout=_CHECK_TIMEOUT_SEC)
        result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return result
    except asyncio.TimeoutError:
        return ServiceHealth(
            status="unreachable",
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            message=f"{name} check timed out after {_CHECK_TIMEOUT_SEC}s",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Health check %s failed: %s", name, e)
        return ServiceHealth(
            status="unreachable",
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            message=str(e),
        )


async def _check_database(db: AsyncSession) -> ServiceHealth:
    result = await db.execute(text("SELECT 1"))
    result.scalar_one()
    return ServiceHealth(status="ok", message="postgresql reachable")


async def _check_redis(r: aioredis.Redis) -> ServiceHealth:
    pong = await r.ping()
    if not pong:
        return ServiceHealth(status="unreachable", message="ping returned false")
    return ServiceHealth(status="ok", message="redis reachable")


async def _check_ai_service(ai: AIServiceClient) -> ServiceHealth:
    data = await ai.health()
    overall = data.get("status", "unknown")
    details = {k: v for k, v in data.items() if k != "status"}
    if overall in ("ok", "degraded"):
        return ServiceHealth(
            status=overall,
            message="ai service reachable",
            details=details,
        )
    return ServiceHealth(status="unreachable", message=str(data), details=details)


async def _check_ollama(ai: AIServiceClient) -> ServiceHealth:
    """Ollama is behind the AI service — parse its nested status."""
    data = await ai.health()
    ollama = data.get("ollama") or {}
    status = ollama.get("status", "unknown")
    if status == "ok":
        return ServiceHealth(status="ok", details=ollama)
    return ServiceHealth(
        status="unreachable",
        message=ollama.get("error", "ollama unreachable"),
        details=ollama,
    )


async def _check_qdrant(ai: AIServiceClient) -> ServiceHealth:
    """Qdrant status is reported by the AI service's /health."""
    data = await ai.health()
    qdrant = data.get("qdrant") or {}
    status = qdrant.get("status", "unknown")
    if status == "ok":
        return ServiceHealth(status="ok", details=qdrant)
    return ServiceHealth(
        status="unreachable",
        message="qdrant unreachable — chat will run without RAG",
        details=qdrant,
    )


def _compute_overall(services: dict[str, ServiceHealth]) -> str:
    """Aggregate per-service statuses into a single overall label.

    - Any "unreachable" in a CRITICAL service → ``down``
    - Any "unreachable" in a NON-CRITICAL service → ``degraded``
    - All services report "ok" → ``ok``

    Critical services are ``database`` and ``ai_service`` (which
    transitively covers Ollama). Everything else is optional.
    """
    critical = {"database", "ai_service", "ollama"}
    any_unreachable = False
    critical_down = False
    for name, svc in services.items():
        if svc.status == "unreachable":
            any_unreachable = True
            if name in critical:
                critical_down = True
    if critical_down:
        return "down"
    if any_unreachable:
        return "degraded"
    return "ok"


# ─── Process uptime ─────────────────────────────────────────

_STARTED_AT = time.monotonic()


def _uptime_seconds() -> float:
    return round(time.monotonic() - _STARTED_AT, 1)


def _disk_usage(path: str = "/") -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {
            "path": path,
            "total_gb": round(usage.total / 1_073_741_824, 2),
            "used_gb": round(usage.used / 1_073_741_824, 2),
            "free_gb": round(usage.free / 1_073_741_824, 2),
            "percent_used": round((usage.used / usage.total) * 100, 1),
        }
    except Exception as e:  # noqa: BLE001
        return {"path": path, "error": str(e)}


async def _queue_metrics(r: aioredis.Redis) -> dict[str, Any]:
    """Best-effort Redis queue/key count snapshot."""
    try:
        info = await r.info("keyspace")
        return {"redis_keyspace": info}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# ─── Endpoints ──────────────────────────────────────────────


@router.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Quick health snapshot",
    description=(
        "Returns the status of every dependency (database, Redis, AI service, "
        "Ollama, Qdrant) plus an aggregate `status` field. Designed for load "
        "balancers and the dashboard footer — runs in under 2 seconds even "
        "when a dependency is hung."
    ),
)
async def health(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    ai: AIServiceClient = Depends(get_ai_client),
) -> HealthResponse:
    results = await asyncio.gather(
        _timed(_check_database(db), "database"),
        _timed(_check_redis(r), "redis"),
        _timed(_check_ai_service(ai), "ai_service"),
        _timed(_check_ollama(ai), "ollama"),
        _timed(_check_qdrant(ai), "qdrant"),
    )
    services = {
        "database": results[0],
        "redis": results[1],
        "ai_service": results[2],
        "ollama": results[3],
        "qdrant": results[4],
    }
    return HealthResponse(
        status=_compute_overall(services),
        version="0.1.0",
        timestamp=datetime.now(UTC).isoformat(),
        services=services,
    )


@router.get(
    "/api/health/detailed",
    response_model=DetailedHealthResponse,
    summary="Detailed health metrics",
    description=(
        "Superset of `/api/health` with uptime, process id, disk usage and "
        "queue metrics. Intended for admin/operator use — gated behind the "
        "same rate limit as the rest of the API."
    ),
)
async def health_detailed(
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    ai: AIServiceClient = Depends(get_ai_client),
) -> DetailedHealthResponse:
    quick = await health(db=db, r=r, ai=ai)
    queues = await _queue_metrics(r)
    return DetailedHealthResponse(
        status=quick.status,
        version=quick.version,
        timestamp=quick.timestamp,
        services=quick.services,
        uptime_seconds=_uptime_seconds(),
        process_id=os.getpid(),
        disk=_disk_usage("/"),
        queues=queues,
    )


# ─── Back-compat stub for external LBs that hit /health ────


@router.get("/health", include_in_schema=False)
async def health_root() -> dict[str, str]:
    """Legacy root-level health ping used by some deployment tooling."""
    return {"status": "ok"}
