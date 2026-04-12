"""Maintenance actions for the admin dashboard.

In-process actions (Redis flush, background loop restart, broadcast push)
are real. External actions (pg_dump, docker compose restart, prisma migrate)
are stubs that record a queued `MaintenanceJob` row but never spawn a
subprocess. Each call site returns the same envelope so a real
implementation can be slotted in later.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.background_loops import get_controller
from app.core.config import settings
from app.models.admin import MaintenanceJob, SystemBroadcast
from app.models.owner import Owner
from app.services.push import get_push_service

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return secrets.token_urlsafe(16)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _record_job(
    db: AsyncSession,
    *,
    job_type: str,
    started_by: str,
    status: str,
    target: str | None = None,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    completed: bool = False,
) -> MaintenanceJob:
    job = MaintenanceJob(
        id=_new_id(),
        job_type=job_type,
        target=target,
        status=status,
        result=result,
        error_message=error_message,
        started_by=started_by,
        started_at=_utcnow(),
        completed_at=_utcnow() if completed else None,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


# ─── Real, in-process actions ────────────────────────────


async def clear_redis_cache(
    db: AsyncSession, admin_username: str, pattern: str | None = None
) -> MaintenanceJob:
    client: aioredis.Redis | None = None
    deleted = 0
    error: str | None = None
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        if not pattern or pattern == "*":
            await client.flushdb()
            deleted = -1  # whole DB
        else:
            async for key in client.scan_iter(match=pattern, count=500):
                await client.delete(key)
                deleted += 1
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        logger.exception("Admin cache flush failed")
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass

    if error is not None:
        return await _record_job(
            db,
            job_type="clear_cache",
            started_by=admin_username,
            status="failed",
            target=pattern,
            error_message=error,
            completed=True,
        )
    return await _record_job(
        db,
        job_type="clear_cache",
        started_by=admin_username,
        status="completed",
        target=pattern,
        result={"deleted": deleted, "pattern": pattern or "*"},
        completed=True,
    )


async def restart_background_loops(
    db: AsyncSession, admin_username: str
) -> MaintenanceJob:
    controller = get_controller()
    if controller is None:
        return await _record_job(
            db,
            job_type="restart_loops",
            started_by=admin_username,
            status="failed",
            error_message="Background loop controller is not initialized",
            completed=True,
        )
    try:
        names = await controller.restart_all()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Admin background loop restart failed")
        return await _record_job(
            db,
            job_type="restart_loops",
            started_by=admin_username,
            status="failed",
            error_message=str(exc),
            completed=True,
        )
    return await _record_job(
        db,
        job_type="restart_loops",
        started_by=admin_username,
        status="completed",
        result={"loops": names, "count": len(names)},
        completed=True,
    )


async def broadcast_notification(
    db: AsyncSession, payload: Any, admin_username: str
) -> SystemBroadcast:
    severity = getattr(payload, "severity", "info") or "info"
    if severity not in ("info", "warning", "critical"):
        severity = "info"

    broadcast = SystemBroadcast(
        id=_new_id(),
        title=payload.title,
        body=payload.body,
        severity=severity,
        push_sent=False,
        push_count=0,
        created_by=admin_username,
        created_at=_utcnow(),
        expires_at=getattr(payload, "expires_at", None),
        active=True,
    )
    db.add(broadcast)
    await db.commit()
    await db.refresh(broadcast)

    if getattr(payload, "send_push", False):
        push = get_push_service()
        if push.configured:
            owner_ids = (await db.execute(select(Owner.id))).scalars().all()
            total = 0
            for oid in owner_ids:
                try:
                    sent = await push.send_to_owner(
                        owner_id=oid,
                        title=broadcast.title,
                        body=broadcast.body,
                        db=db,
                        data={"broadcast_id": broadcast.id, "severity": severity},
                        tag=f"broadcast-{broadcast.id}",
                    )
                    total += sent
                except Exception:
                    logger.exception("Broadcast push to owner %s failed", oid)
            broadcast.push_sent = total > 0
            broadcast.push_count = total
            await db.commit()
            await db.refresh(broadcast)
        else:
            logger.warning("Broadcast %s requested push but service is not configured", broadcast.id)

    return broadcast


async def list_active_broadcasts(db: AsyncSession, limit: int = 50) -> list[SystemBroadcast]:
    result = await db.execute(
        select(SystemBroadcast)
        .order_by(SystemBroadcast.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def dismiss_broadcast(db: AsyncSession, broadcast_id: str) -> bool:
    broadcast = await db.scalar(
        select(SystemBroadcast).where(SystemBroadcast.id == broadcast_id)
    )
    if broadcast is None:
        return False
    broadcast.active = False
    await db.commit()
    return True


# ─── Stubs (no subprocess) ───────────────────────────────


async def trigger_backup(db: AsyncSession, admin_username: str) -> MaintenanceJob:
    logger.warning("Admin backup requested by %s — stub only", admin_username)
    return await _record_job(
        db,
        job_type="backup",
        started_by=admin_username,
        status="queued",
        result={
            "message": "Stub: real pg_dump implementation pending",
            "would_run": "pg_dump $DATABASE_URL > $ADMIN_BACKUP_DIR/replica-{ts}.sql",
        },
    )


async def restart_service(
    db: AsyncSession, service: str, admin_username: str
) -> MaintenanceJob:
    logger.warning("Admin service restart requested for %s by %s — stub only", service, admin_username)
    return await _record_job(
        db,
        job_type="restart_service",
        started_by=admin_username,
        status="queued",
        target=service,
        result={
            "message": f"Stub: would run docker compose restart {service}",
        },
    )


async def run_migrations(db: AsyncSession, admin_username: str) -> MaintenanceJob:
    logger.warning("Admin migration requested by %s — stub only", admin_username)
    return await _record_job(
        db,
        job_type="migrate",
        started_by=admin_username,
        status="queued",
        result={
            "message": "Stub: would run npx prisma migrate deploy",
        },
    )


async def list_jobs(db: AsyncSession, limit: int = 50) -> list[MaintenanceJob]:
    result = await db.execute(
        select(MaintenanceJob).order_by(MaintenanceJob.started_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
