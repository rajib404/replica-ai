from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.security import decode_token

bearer_scheme = HTTPBearer()


@dataclass
class AuthContext:
    """Resolved identity from a valid JWT."""

    subject_id: str  # owner_id
    role: str  # "owner" | "instance" | "family_member"
    instance_id: str | None = None


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthContext:
    """Dependency that validates the JWT and returns an AuthContext.

    Rejects expired, malformed, or non-access tokens.
    """
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type must be 'access'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthContext(
        subject_id=payload["sub"],
        role=payload.get("role", "owner"),
        instance_id=payload.get("instance_id"),
    )


def require_role(*allowed_roles: str):
    """Returns a dependency that restricts access to specific roles.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role("owner"))])
    """

    async def _check(auth: AuthContext = Depends(require_auth)) -> AuthContext:
        if auth.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{auth.role}' is not allowed. Required: {', '.join(allowed_roles)}",
            )
        return auth

    return _check
