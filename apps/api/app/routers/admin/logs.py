"""Admin in-memory logs viewer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.admin_auth import AdminContext, require_admin
from app.models.admin_schemas import LogEntry, LogsResponse
from app.services.admin.log_buffer import get_log_buffer, query_logs

router = APIRouter()


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    level: str | None = Query(default=None),
    logger: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    _: AdminContext = Depends(require_admin),
) -> LogsResponse:
    items, total = query_logs(
        level=level, logger_substring=logger, search=search, limit=limit
    )
    handler = get_log_buffer()
    capacity = handler.capacity if handler is not None else 0
    return LogsResponse(
        items=[LogEntry(**i) for i in items],
        total=total,
        capacity=capacity,
    )
