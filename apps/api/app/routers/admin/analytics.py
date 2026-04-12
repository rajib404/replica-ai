"""Admin analytics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import AdminContext, require_admin
from app.core.database import get_db
from app.models.admin_schemas import (
    ExternalLLMUsagePoint,
    ExternalLLMUsageResponse,
    KnowledgeTypeBucket,
    KnowledgeTypeResponse,
    StorageProjectionPoint,
    StorageProjectionResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
)
from app.services.admin import analytics

router = APIRouter(prefix="/analytics")


@router.get("/dau", response_model=TimeSeriesResponse)
async def dau(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> TimeSeriesResponse:
    points = await analytics.daily_active_users(db, days=days)
    return TimeSeriesResponse(points=[TimeSeriesPoint(**p) for p in points])


@router.get("/messages", response_model=TimeSeriesResponse)
async def messages(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> TimeSeriesResponse:
    points = await analytics.message_volume(db, days=days)
    return TimeSeriesResponse(points=[TimeSeriesPoint(**p) for p in points])


@router.get("/knowledge-rate", response_model=TimeSeriesResponse)
async def knowledge_rate(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> TimeSeriesResponse:
    points = await analytics.knowledge_ingestion_rate(db, days=days)
    return TimeSeriesResponse(points=[TimeSeriesPoint(**p) for p in points])


@router.get("/knowledge-types", response_model=KnowledgeTypeResponse)
async def knowledge_types(
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> KnowledgeTypeResponse:
    items = await analytics.knowledge_type_distribution(db)
    return KnowledgeTypeResponse(items=[KnowledgeTypeBucket(**i) for i in items])


@router.get("/external-llm", response_model=ExternalLLMUsageResponse)
async def external_llm(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> ExternalLLMUsageResponse:
    items = await analytics.external_llm_usage(db, days=days)
    return ExternalLLMUsageResponse(items=[ExternalLLMUsagePoint(**i) for i in items])


@router.get("/storage", response_model=StorageProjectionResponse)
async def storage(
    days: int = Query(default=30, ge=1, le=365),
    project_days: int = Query(default=90, ge=0, le=365),
    db: AsyncSession = Depends(get_db),
    _: AdminContext = Depends(require_admin),
) -> StorageProjectionResponse:
    points = await analytics.storage_growth_projection(db, days=days, project_days=project_days)
    return StorageProjectionResponse(points=[StorageProjectionPoint(**p) for p in points])
