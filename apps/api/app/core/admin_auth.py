"""Admin dashboard auth — fully separate from owner JWT.

Uses a dedicated JWT secret (`settings.admin_jwt_secret`) so that
even if the admin secret leaks the owner sessions remain unaffected.
Includes an optional IP allowlist enforced on every admin route.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AdminContext:
    """Resolved admin identity from a valid admin JWT."""

    username: str
    issued_at: datetime
    expires_at: datetime


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def verify_admin_credentials(username: str, password: str) -> bool:
    """Validate username + plaintext password against the env-configured admin."""
    if not settings.admin_enabled or not settings.admin_user or not settings.admin_pass_hash:
        return False
    if not _constant_time_eq(username, settings.admin_user):
        return False
    try:
        return bcrypt.checkpw(password.encode(), settings.admin_pass_hash.encode())
    except (ValueError, TypeError):
        return False


def create_admin_token(username: str) -> tuple[str, datetime]:
    """Mint a short-lived JWT signed with the admin secret."""
    if not settings.admin_jwt_secret:
        raise RuntimeError("ADMIN_JWT_SECRET is not configured")
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.admin_jwt_expire_minutes)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "admin",
    }
    token = jwt.encode(payload, settings.admin_jwt_secret, algorithm="HS256")
    return token, exp


def _check_ip_allowlist(client_ip: str | None) -> None:
    if not settings.admin_ip_allowlist:
        return
    if client_ip is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin: client IP unavailable",
        )
    try:
        ip = ip_address(client_ip)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin: invalid client IP",
        ) from exc
    for cidr in settings.admin_ip_allowlist:
        try:
            if ip in ip_network(cidr.strip(), strict=False):
                return
        except ValueError:
            logger.warning("Admin: malformed CIDR %r in allowlist; skipping", cidr)
            continue
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin: IP not in allowlist",
    )


def check_admin_ip(request: Request) -> None:
    """Convenience hook for unauthenticated admin endpoints (login)."""
    _check_ip_allowlist(request.client.host if request.client else None)


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AdminContext:
    """FastAPI dependency that gates an admin route."""
    if not settings.admin_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin disabled")

    _check_ip_allowlist(request.client.host if request.client else None)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials, settings.admin_jwt_secret, algorithms=["HS256"]
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid admin token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AdminContext(
        username=payload["sub"],
        issued_at=datetime.fromtimestamp(payload["iat"], UTC),
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )
