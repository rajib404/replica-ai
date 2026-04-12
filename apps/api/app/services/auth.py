import base64
import io
from datetime import UTC, datetime

import qrcode
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy import select
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
    RefreshResponse,
    SetupRequest,
    SetupResponse,
    TokenPair,
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

    owner_id = _generate_cuid()
    owner = Owner(
        id=owner_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        preferred_language=request.preferred_language,
        auth_secret_hash=secret_hash,
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


async def verify_identity(
    request: VerifyRequest, db: AsyncSession, redis: Redis
) -> VerifyResponse:
    """Run a verification challenge against the owner's stored credentials."""
    allowed, wait_seconds = await check_rate_limit(redis, request.owner_id)
    if not allowed:
        return VerifyResponse(
            verified=False,
            message=f"Too many attempts. Try again in {wait_seconds} seconds.",
        )

    owner_result = await db.execute(select(Owner).where(Owner.id == request.owner_id))
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        return VerifyResponse(verified=False, message="Owner not found")

    verified = False

    if request.verification_type in ("secret_word", "secret_event"):
        if not request.value:
            return VerifyResponse(verified=False, message="Value is required for secret verification")
        if not owner.auth_secret_hash:
            return VerifyResponse(verified=False, message="No secret configured for this owner")
        verified = verify_secret(request.value, owner.auth_secret_hash)

    elif request.verification_type == "voice_match":
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

    elif request.verification_type == "face_match":
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
        count = await record_attempt(redis, request.owner_id)
        remaining = settings.verify_max_attempts - count
        return VerifyResponse(
            verified=False,
            message=f"Verification failed. {max(remaining, 0)} attempts remaining.",
        )

    await clear_attempts(redis, request.owner_id)

    access_token = create_access_token(subject=owner.id, role="owner")
    refresh_token = create_refresh_token(subject=owner.id, role="owner")

    return VerifyResponse(
        verified=True,
        message="Identity verified",
        tokens=TokenPair(access_token=access_token, refresh_token=refresh_token),
    )


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
