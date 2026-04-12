"""Admin overview endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import AdminContext, require_admin
from app.core.database import get_db
from app.models.admin_schemas import SystemOverviewResponse
from app.services.admin import stats

router = APIRouter()


@router.get("/overview", response_model=SystemOverviewResponse)
async def get_overview(
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> SystemOverviewResponse:
    snapshot = await stats.get_system_overview(db)
    return SystemOverviewResponse(**snapshot)
