from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_auth, require_role
from app.core.database import get_db
from app.models.instance import (
    HeartbeatResponse,
    InstanceListResponse,
    InstanceRegisteredResponse,
    InstanceResponse,
    RegisterInstanceRequest,
)
from app.services.instance_manager import InstanceRegistry

router = APIRouter(prefix="/api/instances", tags=["instances"])

registry = InstanceRegistry()


@router.post("/register", status_code=201, response_model=InstanceRegisteredResponse)
async def register_instance(
    body: RegisterInstanceRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> InstanceRegisteredResponse:
    """Register a new model instance for this owner."""
    result = await registry.register_instance(
        owner_id=auth.subject_id,
        instance_type=body.instance_type,
        hostname=body.hostname,
        api_url=body.api_url,
        capabilities=body.capabilities,
        db=db,
    )
    return InstanceRegisteredResponse(**result)


@router.get("", response_model=InstanceListResponse)
async def list_instances(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> InstanceListResponse:
    """List all instances for this owner with live status checks."""
    instances = await registry.discover_instances(auth.subject_id, db)
    return InstanceListResponse(instances=instances, total=len(instances))


@router.post("/{instance_id}/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    instance_id: str,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> HeartbeatResponse:
    """Record a heartbeat for an instance. Accepts both owner and instance roles."""
    try:
        result = await registry.record_heartbeat(instance_id, auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return HeartbeatResponse(
        status=result.status,
        last_heartbeat_at=result.last_heartbeat_at,
    )


@router.put("/{instance_id}/promote", response_model=InstanceResponse)
async def promote_instance(
    instance_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """Promote an instance to primary."""
    try:
        return await registry.promote_to_primary(instance_id, auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{instance_id}", status_code=204)
async def delete_instance(
    instance_id: str,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deregister an instance."""
    try:
        await registry.deregister_instance(instance_id, auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
