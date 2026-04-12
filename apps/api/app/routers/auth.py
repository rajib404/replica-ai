from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.auth import (
    ConnectRequest,
    ConnectResponse,
    RefreshRequest,
    RefreshResponse,
    SetupRequest,
    SetupResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.auth import (
    connect_instance,
    refresh_tokens,
    setup_owner,
    store_refresh_token,
    verify_identity,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/setup", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
async def auth_setup(
    request: SetupRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> SetupResponse:
    """First-time owner setup. Creates profile, returns JWT pair and QR code."""
    try:
        result = await setup_owner(request, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await store_refresh_token(redis, result.tokens.refresh_token, result.owner_id)
    return result


@router.post("/connect", response_model=ConnectResponse)
async def auth_connect(
    request: ConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> ConnectResponse:
    """Connect a new device/instance via QR code or link."""
    try:
        return await connect_instance(request, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post("/verify", response_model=VerifyResponse)
async def auth_verify(
    request: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> VerifyResponse:
    """Verify owner identity via secret word, event, voice, or face."""
    result = await verify_identity(request, db, redis)
    if result.verified and result.tokens:
        await store_refresh_token(redis, result.tokens.refresh_token, request.owner_id)
    return result


@router.post("/refresh", response_model=RefreshResponse)
async def auth_refresh(
    request: RefreshRequest,
    redis: Redis = Depends(get_redis),
) -> RefreshResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        return await refresh_tokens(request.refresh_token, redis)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
