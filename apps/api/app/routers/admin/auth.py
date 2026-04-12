"""Admin login + session lookup."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.admin_auth import (
    AdminContext,
    check_admin_ip,
    create_admin_token,
    require_admin,
    verify_admin_credentials,
)
from app.core.config import settings
from app.models.admin_schemas import AdminLoginRequest, AdminLoginResponse, AdminSessionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest, request: Request) -> AdminLoginResponse:
    if not settings.admin_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin disabled")
    check_admin_ip(request)

    if not verify_admin_credentials(payload.username, payload.password):
        client_host = request.client.host if request.client else "unknown"
        logger.warning(
            "Admin login failed for %r from %s", payload.username, client_host
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )

    token, expires_at = create_admin_token(payload.username)
    logger.info("Admin login succeeded for %r", payload.username)
    return AdminLoginResponse(access_token=token, expires_at=expires_at)


@router.get("/me", response_model=AdminSessionResponse)
async def admin_me(ctx: AdminContext = Depends(require_admin)) -> AdminSessionResponse:
    return AdminSessionResponse(username=ctx.username, expires_at=ctx.expires_at)
