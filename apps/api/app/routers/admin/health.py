"""Admin service health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import AdminContext, require_admin
from app.core.database import get_db
from app.models.admin_schemas import HealthSnapshotResponse, ServiceHealthEntry
from app.services.admin import health as health_service

router = APIRouter()


@router.get("/health/services", response_model=HealthSnapshotResponse)
async def get_service_health(
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> HealthSnapshotResponse:
    entries = await health_service.collect_health_snapshot(db)
    return HealthSnapshotResponse(items=[ServiceHealthEntry(**e) for e in entries])
