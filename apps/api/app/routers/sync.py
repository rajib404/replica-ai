from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.sync import (
    ResolveConflictRequest,
    StartSyncRequest,
    SyncConflictResponse,
    SyncHistoryResponse,
    SyncStartedResponse,
    SyncStatusResponse,
)
from app.services.sync_engine import SyncEngine

router = APIRouter(prefix="/api/sync", tags=["sync"])

engine = SyncEngine()


@router.post("/start", status_code=202, response_model=SyncStartedResponse)
async def start_sync(
    body: StartSyncRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> SyncStartedResponse:
    """Trigger a sync between two instances."""
    try:
        if body.sync_type == "full":
            result = await engine.full_sync(
                source_instance_id=body.source_instance_id,
                target_instance_id=body.target_instance_id,
                owner_id=auth.subject_id,
                db=db,
            )
        elif body.sync_type == "incremental":
            if not body.since:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'since' is required for incremental sync",
                )
            result = await engine.incremental_sync(
                source_instance_id=body.source_instance_id,
                target_instance_id=body.target_instance_id,
                owner_id=auth.subject_id,
                since=body.since,
                db=db,
            )
        elif body.sync_type == "model_weights":
            result = await engine.sync_model_weights(
                source_instance_id=body.source_instance_id,
                target_instance_id=body.target_instance_id,
                owner_id=auth.subject_id,
                db=db,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown sync type: {body.sync_type}",
            )

        return SyncStartedResponse(
            sync_id=result.id,
            status=result.status,
            message=f"{body.sync_type} sync completed with {result.entries_synced} entries",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e


@router.get("/status/{sync_id}", response_model=SyncStatusResponse)
async def get_sync_status(
    sync_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> SyncStatusResponse:
    """Check the progress and status of a sync operation."""
    try:
        result = await engine.get_sync_status(sync_id, auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e

    return SyncStatusResponse(sync=result, conflicts=result.conflicts)


@router.get("/history", response_model=SyncHistoryResponse)
async def get_sync_history(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> SyncHistoryResponse:
    """Get sync log history with optional status filter."""
    syncs, total = await engine.get_sync_history(
        owner_id=auth.subject_id,
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )
    return SyncHistoryResponse(syncs=syncs, total=total)


@router.post(
    "/resolve-conflict/{conflict_id}",
    response_model=SyncConflictResponse,
)
async def resolve_conflict(
    conflict_id: str,
    body: ResolveConflictRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> SyncConflictResponse:
    """Resolve a sync conflict by choosing which version to keep."""
    try:
        return await engine.resolve_conflict(
            conflict_id=conflict_id,
            resolution=body.resolution,
            owner_id=auth.subject_id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
