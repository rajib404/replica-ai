"""Admin maintenance endpoints (real + stubbed actions)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import AdminContext, require_admin
from app.core.database import get_db
from app.models.admin import MaintenanceJob, SystemBroadcast
from app.models.admin_schemas import (
    BroadcastListResponse,
    BroadcastRequest,
    BroadcastResponse,
    ClearCacheRequest,
    MaintenanceJobListResponse,
    MaintenanceJobResponse,
    RestartServiceRequest,
)
from app.services.admin import maintenance

router = APIRouter(prefix="/maintenance")


def _serialize_job(job: MaintenanceJob) -> MaintenanceJobResponse:
    return MaintenanceJobResponse(
        id=job.id,
        job_type=job.job_type,
        target=job.target,
        status=job.status,
        result=job.result,
        error_message=job.error_message,
        started_by=job.started_by,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _serialize_broadcast(b: SystemBroadcast) -> BroadcastResponse:
    return BroadcastResponse(
        id=b.id,
        title=b.title,
        body=b.body,
        severity=b.severity,
        push_sent=b.push_sent,
        push_count=b.push_count,
        created_by=b.created_by,
        created_at=b.created_at,
        expires_at=b.expires_at,
        active=b.active,
    )


@router.post("/backup", response_model=MaintenanceJobResponse)
async def backup(
    db: AsyncSession = Depends(get_db),
    ctx: AdminContext = Depends(require_admin),
) -> MaintenanceJobResponse:
    job = await maintenance.trigger_backup(db, ctx.username)
    return _serialize_job(job)


@router.post("/restart-service", response_model=MaintenanceJobResponse)
async def restart_service(
    payload: RestartServiceRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AdminContext = Depends(require_admin),
) -> MaintenanceJobResponse:
    job = await maintenance.restart_service(db, payload.service, ctx.username)
    return _serialize_job(job)


@router.post("/migrate", response_model=MaintenanceJobResponse)
async def migrate(
    db: AsyncSession = Depends(get_db),
    ctx: AdminContext = Depends(require_admin),
) -> MaintenanceJobResponse:
    job = await maintenance.run_migrations(db, ctx.username)
    return _serialize_job(job)


@router.post("/clear-cache", response_model=MaintenanceJobResponse)
async def clear_cache(
    payload: ClearCacheRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AdminContext = Depends(require_admin),
) -> MaintenanceJobResponse:
    job = await maintenance.clear_redis_cache(db, ctx.username, pattern=payload.pattern)
    return _serialize_job(job)


@router.post("/restart-loops", response_model=MaintenanceJobResponse)
async def restart_loops(
    db: AsyncSession = Depends(get_db),
    ctx: AdminContext = Depends(require_admin),
) -> MaintenanceJobResponse:
    job = await maintenance.restart_background_loops(db, ctx.username)
    return _serialize_job(job)


@router.post("/broadcast", response_model=BroadcastResponse)
async def send_broadcast(
    payload: BroadcastRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AdminContext = Depends(require_admin),
) -> BroadcastResponse:
    broadcast = await maintenance.broadcast_notification(db, payload, ctx.username)
    return _serialize_broadcast(broadcast)


@router.get("/jobs", response_model=MaintenanceJobListResponse)
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> MaintenanceJobListResponse:
    jobs = await maintenance.list_jobs(db, limit=limit)
    return MaintenanceJobListResponse(items=[_serialize_job(j) for j in jobs])


@router.get("/broadcasts", response_model=BroadcastListResponse)
async def list_broadcasts(
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> BroadcastListResponse:
    broadcasts = await maintenance.list_active_broadcasts(db, limit=limit)
    return BroadcastListResponse(items=[_serialize_broadcast(b) for b in broadcasts])
