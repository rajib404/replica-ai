"""Web Push subscription + notification endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.config import settings
from app.core.database import get_db
from app.models.push import (
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    PushTestRequest,
    PushUnsubscribeRequest,
    PushVapidKeyResponse,
)
from app.services.push import get_push_service

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key", response_model=PushVapidKeyResponse)
async def get_vapid_public_key() -> PushVapidKeyResponse:
    """Return the VAPID public key clients need to subscribe.

    The public key is non-sensitive — exposing it is required by the spec.
    """
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured on the server",
        )
    return PushVapidKeyResponse(key=settings.vapid_public_key)


@router.post(
    "/subscribe",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def subscribe(
    payload: PushSubscriptionCreate,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> PushSubscriptionResponse:
    """Register a Web Push subscription for the authenticated owner."""
    service = get_push_service()
    sub = await service.subscribe(auth.subject_id, payload, db)
    return PushSubscriptionResponse(
        id=sub.id, endpoint=sub.endpoint, created_at=sub.created_at
    )


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: PushUnsubscribeRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a previously registered subscription."""
    service = get_push_service()
    removed = await service.unsubscribe(auth.subject_id, payload.endpoint, db)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )


@router.post("/test")
async def send_test(
    payload: PushTestRequest,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | bool]:
    """Send a test notification to every subscription belonging to the caller."""
    service = get_push_service()
    if not service.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured on the server",
        )
    sent = await service.send_to_owner(
        owner_id=auth.subject_id,
        title=payload.title,
        body=payload.body,
        db=db,
        data={"url": payload.url} if payload.url else None,
        tag="test",
    )
    return {"sent": sent, "ok": sent > 0}
