import base64
import io
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
import qrcode
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import check_rate_limit, clear_attempts, record_attempt
from app.core.security import (
    create_access_token,
    create_connect_token,
    create_refresh_token,
    decode_token,
    hash_secret,
    verify_secret,
)
from app.models.auth import (
    ConnectRequest,
    ConnectResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    ProfileResponse,
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
from app.models.owner import InstanceType, ModelInstance, Owner


def _generate_cuid() -> str:
    """Generate a cuid-like ID. Uses timestamp + random hex for uniqueness."""
    import secrets
    import time

    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _generate_qr_base64(url: str) -> str:
    """Generate a QR code image as a base64-encoded PNG string."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


async def setup_owner(request: SetupRequest, db: AsyncSession) -> SetupResponse:
    """First-time owner setup: create profile, generate tokens and QR code."""
    existing = await db.execute(select(Owner).where(Owner.email == request.email))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("An owner with this email already exists")

    secret_hash = None
    if request.secret_word:
        secret_hash = hash_secret(request.secret_word)
    elif request.secret_event:
        secret_hash = hash_secret(request.secret_event)

    password_hash = hash_secret(request.password) if request.password else None

    owner_id = _generate_cuid()
    owner = Owner(
        id=owner_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        preferred_language=request.preferred_language,
        auth_secret_hash=secret_hash,
        password_hash=password_hash,
    )
    db.add(owner)
    await db.commit()
    await db.refresh(owner)

    access_token = create_access_token(subject=owner.id, role="owner")
    refresh_token = create_refresh_token(subject=owner.id, role="owner")

    connect_token = create_connect_token(owner.id)
    connect_url = f"{settings.host_url}/connect?token={connect_token}"
    qr_base64 = _generate_qr_base64(connect_url)

    return SetupResponse(
        owner_id=owner.id,
        tokens=TokenPair(access_token=access_token, refresh_token=refresh_token),
        connect_url=connect_url,
        qr_code_base64=qr_base64,
    )


async def store_refresh_token(redis: Redis, token: str, owner_id: str) -> None:
    """Store refresh token in Redis with TTL."""
    ttl = settings.refresh_token_expire_days * 86400
    await redis.setex(f"refresh:{owner_id}:{token[:16]}", ttl, token)


async def connect_instance(
    request: ConnectRequest, db: AsyncSession
) -> ConnectResponse:
    """Validate a connect token and register a new model instance."""
    try:
        payload = decode_token(request.token)
    except JWTError as e:
        raise ValueError(f"Invalid or expired connection token: {e}") from e

    if payload.get("type") != "connect":
        raise ValueError("Token is not a connection token")

    owner_id = payload["sub"]

    owner = await db.execute(select(Owner).where(Owner.id == owner_id))
    if owner.scalar_one_or_none() is None:
        raise ValueError("Owner not found")

    instance_id = _generate_cuid()
    instance = ModelInstance(
        id=instance_id,
        owner_id=owner_id,
        instance_type=InstanceType(request.instance_type),
        hostname=request.hostname,
        last_sync_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(instance)
    await db.commit()

    session_token = create_access_token(
        subject=owner_id,
        role="instance",
        extra={"instance_id": instance_id},
    )

    return ConnectResponse(
        session_token=session_token,
        owner_id=owner_id,
        instance_id=instance_id,
    )


async def _resolve_verification(
    owner: Owner, verification_type: str, value: str | None, redis: Redis
) -> VerifyResponse:
    """Run a verification challenge against an already-resolved owner's credentials."""
    allowed, wait_seconds = await check_rate_limit(redis, owner.id)
    if not allowed:
        return VerifyResponse(
            verified=False,
            message=f"Too many attempts. Try again in {wait_seconds} seconds.",
        )

    verified = False

    if verification_type == "password":
        if not value:
            return VerifyResponse(verified=False, message="Password is required")
        if not owner.password_hash:
            return VerifyResponse(
                verified=False,
                message=(
                    "No password set for this account. Sign in with your secret "
                    "word/event instead, or set a password from Settings once signed in."
                ),
            )
        verified = verify_secret(value, owner.password_hash)

    elif verification_type in ("secret_word", "secret_event"):
        if not value:
            return VerifyResponse(
                verified=False, message="Value is required for secret verification"
            )
        if not owner.auth_secret_hash:
            return VerifyResponse(verified=False, message="No secret configured for this owner")
        verified = verify_secret(value, owner.auth_secret_hash)

    elif verification_type == "voice_match":
        # Voice verification requires audio data via the /api/verify/voice/check endpoint.
        # The /api/auth/verify endpoint doesn't accept file uploads,
        # so voice_match here checks only that a profile is enrolled.
        if not owner.voice_profile_ref:
            return VerifyResponse(
                verified=False,
                message="No voice profile enrolled. Use /api/verify/voice/enroll first.",
            )
        return VerifyResponse(
            verified=False,
            message="Voice verification requires audio. Use /api/verify/voice/check endpoint.",
        )

    elif verification_type == "face_match":
        if not owner.face_profile_ref:
            return VerifyResponse(
                verified=False,
                message="No face profile enrolled. Use /api/verify/face/enroll first.",
            )
        return VerifyResponse(
            verified=False,
            message="Face verification requires an image. Use /api/verify/face/check endpoint.",
        )

    if not verified:
        count = await record_attempt(redis, owner.id)
        remaining = settings.verify_max_attempts - count
        return VerifyResponse(
            verified=False,
            message=f"Verification failed. {max(remaining, 0)} attempts remaining.",
        )

    await clear_attempts(redis, owner.id)

    access_token = create_access_token(subject=owner.id, role="owner")
    refresh_token = create_refresh_token(subject=owner.id, role="owner")

    return VerifyResponse(
        verified=True,
        message="Identity verified",
        tokens=TokenPair(access_token=access_token, refresh_token=refresh_token),
    )


async def verify_identity(
    request: VerifyRequest, db: AsyncSession, redis: Redis
) -> VerifyResponse:
    """Run a verification challenge against the owner's stored credentials."""
    owner_result = await db.execute(select(Owner).where(Owner.id == request.owner_id))
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        return VerifyResponse(verified=False, message="Owner not found")

    return await _resolve_verification(owner, request.verification_type, request.value, redis)


async def login_owner(request: LoginRequest, db: AsyncSession, redis: Redis) -> LoginResponse:
    """Look up an existing owner by email and verify their secret word/event."""
    owner_result = await db.execute(
        select(Owner).where(func.lower(Owner.email) == request.email.strip().lower())
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        return LoginResponse(verified=False, message="No account found for that email.")

    result = await _resolve_verification(owner, request.verification_type, request.value, redis)
    return LoginResponse(
        verified=result.verified,
        message=result.message,
        owner_id=owner.id if result.verified else None,
        tokens=result.tokens,
    )


def _to_profile(owner: Owner) -> ProfileResponse:
    return ProfileResponse(
        owner_id=owner.id,
        name=owner.name,
        email=owner.email,
        phone=owner.phone,
        preferred_language=owner.preferred_language,
        has_password=owner.password_hash is not None,
        google_linked=owner.google_id is not None,
    )


async def get_profile(owner_id: str, db: AsyncSession) -> ProfileResponse:
    """Fetch the signed-in owner's profile."""
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise ValueError("Owner not found")
    return _to_profile(owner)


async def update_profile(
    owner_id: str, request: UpdateProfileRequest, db: AsyncSession
) -> ProfileResponse:
    """Update the signed-in owner's name, email, or phone."""
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        raise ValueError("Owner not found")

    if request.email != owner.email:
        existing = await db.execute(
            select(Owner).where(Owner.email == request.email, Owner.id != owner_id)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("An owner with this email already exists")

    owner.name = request.name
    owner.email = request.email
    owner.phone = request.phone
    await db.commit()
    await db.refresh(owner)

    return _to_profile(owner)


async def set_password(
    owner_id: str, request: SetPasswordRequest, db: AsyncSession
) -> SetPasswordResponse:
    """Set or change an owner's password. Requires the current password if one is already set."""
    result = await db.execute(select(Owner).where(Owner.id == owner_id))
    owner = result.scalar_one_or_none()
    if owner is None:
        return SetPasswordResponse(success=False, message="Owner not found")

    if owner.password_hash:
        if not request.current_password or not verify_secret(
            request.current_password, owner.password_hash
        ):
            return SetPasswordResponse(success=False, message="Current password is incorrect")

    owner.password_hash = hash_secret(request.new_password)
    await db.commit()

    return SetPasswordResponse(success=True, message="Password updated")


async def logout(refresh_token: str, redis: Redis) -> LogoutResponse:
    """Revoke a refresh token so it can no longer be used to obtain new access tokens."""
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        return LogoutResponse(success=True)

    subject = payload.get("sub")
    if subject:
        await redis.delete(f"refresh:{subject}:{refresh_token[:16]}")

    return LogoutResponse(success=True)


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def build_google_auth_url(state: str) -> str:
    """Build the URL that starts Google's OAuth consent flow."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_google_code(code: str) -> dict:
    """Exchange an OAuth authorization code for the signed-in user's Google profile."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        google_access_token = token_resp.json()["access_token"]

        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        userinfo_resp.raise_for_status()
        return userinfo_resp.json()


async def login_or_create_owner_via_google(userinfo: dict, db: AsyncSession) -> Owner:
    """Find the owner linked to this Google account, link an existing email match, or create one."""
    google_id = userinfo["sub"]
    email = (userinfo.get("email") or "").strip().lower()

    result = await db.execute(select(Owner).where(Owner.google_id == google_id))
    owner = result.scalar_one_or_none()
    if owner is not None:
        return owner

    if email:
        result = await db.execute(select(Owner).where(func.lower(Owner.email) == email))
        owner = result.scalar_one_or_none()
        if owner is not None:
            owner.google_id = google_id
            await db.commit()
            await db.refresh(owner)
            return owner

    owner_id = _generate_cuid()
    owner = Owner(
        id=owner_id,
        name=userinfo.get("name") or (email.split("@")[0] if email else "New Owner"),
        email=email or f"{owner_id}@replica-ai.local",
        preferred_language="en",
        google_id=google_id,
    )
    db.add(owner)
    await db.commit()
    await db.refresh(owner)
    return owner


async def refresh_tokens(token: str, redis: Redis) -> RefreshResponse:
    """Validate a refresh token and issue a new access + refresh pair."""
    try:
        payload = decode_token(token)
    except JWTError as e:
        raise ValueError(f"Invalid or expired refresh token: {e}") from e

    if payload.get("type") != "refresh":
        raise ValueError("Token is not a refresh token")

    subject = payload["sub"]
    role = payload.get("role", "owner")

    # Verify token exists in Redis (not revoked)
    stored = await redis.get(f"refresh:{subject}:{token[:16]}")
    if stored is None:
        raise ValueError("Refresh token has been revoked or expired")

    # Revoke the old refresh token
    await redis.delete(f"refresh:{subject}:{token[:16]}")

    # Issue new pair
    new_access = create_access_token(subject=subject, role=role)
    new_refresh = create_refresh_token(subject=subject, role=role)

    # Store the new refresh token
    await store_refresh_token(redis, new_refresh, subject)

    return RefreshResponse(
        tokens=TokenPair(access_token=new_access, refresh_token=new_refresh),
    )
