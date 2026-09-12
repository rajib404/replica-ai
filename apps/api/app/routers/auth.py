import logging
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_auth
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token
from app.models.auth import (
    ConnectRequest,
    ConnectResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    ProfileResponse,
    RefreshRequest,
    RefreshResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    SetupRequest,
    SetupResponse,
    TokenPair,
    UpdateProfileRequest,
    VerifyRequest,
    VerifyResponse,
)
from app.services.auth import (
    build_google_auth_url,
    connect_instance,
    exchange_google_code,
    get_profile,
    login_or_create_owner_via_google,
    login_owner,
    refresh_tokens,
    set_password,
    setup_owner,
    store_refresh_token,
    update_profile,
    verify_identity,
)
from app.services.auth import (
    logout as logout_service,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


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


@router.post("/login", response_model=LoginResponse)
async def auth_login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> LoginResponse:
    """Sign an existing owner back in via email + secret word/event."""
    result = await login_owner(request, db, redis)
    if result.verified and result.tokens and result.owner_id:
        await store_refresh_token(redis, result.tokens.refresh_token, result.owner_id)
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


@router.post("/logout", response_model=LogoutResponse)
async def auth_logout(
    request: LogoutRequest,
    redis: Redis = Depends(get_redis),
) -> LogoutResponse:
    """Sign out by revoking the given refresh token."""
    return await logout_service(request.refresh_token, redis)


@router.get("/me", response_model=ProfileResponse)
async def auth_get_profile(
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Get the signed-in owner's profile."""
    try:
        return await get_profile(auth.subject_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.put("/profile", response_model=ProfileResponse)
async def auth_update_profile(
    request: UpdateProfileRequest,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update the signed-in owner's name, email, or phone."""
    try:
        return await update_profile(auth.subject_id, request, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.put("/password", response_model=SetPasswordResponse)
async def auth_set_password(
    request: SetPasswordRequest,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> SetPasswordResponse:
    """Set or change the signed-in owner's password."""
    return await set_password(auth.subject_id, request, db)


@router.get("/google/start")
async def auth_google_start(redis: Redis = Depends(get_redis)) -> RedirectResponse:
    """Redirect the browser to Google's OAuth consent screen."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this server.",
        )
    state = secrets.token_urlsafe(24)
    await redis.setex(f"oauth_state:google:{state}", 600, "1")
    return RedirectResponse(build_google_auth_url(state))


@router.get("/google/callback")
async def auth_google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> RedirectResponse:
    """Handle Google's OAuth redirect, sign the owner in, and hand tokens to the web app."""
    login_page = f"{settings.web_app_url}/login"

    if error or not code or not state:
        logger.warning(
            "Google sign-in callback missing required params: error=%r code_present=%s state_present=%s",
            error, bool(code), bool(state),
        )
        return RedirectResponse(f"{login_page}?error=google_sign_in_failed")

    state_key = f"oauth_state:google:{state}"
    if not await redis.get(state_key):
        logger.warning("Google sign-in state token not found/expired in redis: %s", state_key)
        return RedirectResponse(f"{login_page}?error=google_sign_in_expired")
    await redis.delete(state_key)

    try:
        userinfo = await exchange_google_code(code)
        owner = await login_or_create_owner_via_google(userinfo, db)
    except Exception:
        logger.exception("Google sign-in callback failed")
        return RedirectResponse(f"{login_page}?error=google_sign_in_failed")

    access_token = create_access_token(subject=owner.id, role="owner")
    refresh_token = create_refresh_token(subject=owner.id, role="owner")
    await store_refresh_token(redis, refresh_token, owner.id)

    tokens = TokenPair(access_token=access_token, refresh_token=refresh_token)
    fragment = (
        f"access_token={quote(tokens.access_token)}"
        f"&refresh_token={quote(tokens.refresh_token)}"
        f"&owner_id={quote(owner.id)}"
        f"&owner_name={quote(owner.name)}"
    )
    return RedirectResponse(f"{settings.web_app_url}/login/callback#{fragment}")
