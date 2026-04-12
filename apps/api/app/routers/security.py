"""Security endpoints: audit log, 2FA, encryption status, data export & deletion."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_role
from app.core.database import get_db
from app.models.security import (
    AuditLogEntry,
    AuditLogResponse,
    DataDeleteRequest,
    DataDeleteResponse,
    DataExportListResponse,
    DataExportResponse,
    EncryptionStatusResponse,
    TwoFactorDisableRequest,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    TwoFactorVerifyRequest,
    TwoFactorVerifyResponse,
)
from app.services.security import (
    encryption_status,
    get_audit_logger,
    get_data_destroyer,
    get_data_exporter,
    get_two_factor_manager,
)

router = APIRouter(prefix="/api/security", tags=["security"])


def _client_info(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


# ─── Encryption status ──────────────────────────────────────


@router.get("/encryption-status", response_model=EncryptionStatusResponse)
async def get_encryption_status(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> EncryptionStatusResponse:
    info = await encryption_status(db)
    return EncryptionStatusResponse(**info)


# ─── Audit log ──────────────────────────────────────────────


@router.get("/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    category: str | None = Query(default=None),
    action: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> AuditLogResponse:
    logger = get_audit_logger()
    rows, total = await logger.query(
        db,
        owner_id=auth.subject_id,
        category=category,
        action=action,
        outcome=outcome,
        page=page,
        page_size=page_size,
    )
    return AuditLogResponse(
        entries=[
            AuditLogEntry(
                id=r.id,
                owner_id=r.owner_id,
                actor_id=r.actor_id,
                actor_role=r.actor_role,
                action=r.action,
                category=r.category,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                outcome=r.outcome,
                ip_address=r.ip_address,
                user_agent=r.user_agent,
                request_id=r.request_id,
                details=r.details,
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ─── Two-factor authentication ──────────────────────────────


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(
    request: Request,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorSetupResponse:
    manager = get_two_factor_manager()
    try:
        secret, uri, qr, codes = await manager.setup(auth.subject_id, db)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    ip, ua = _client_info(request)
    await get_audit_logger().log(
        db,
        action="2fa_setup_initiated",
        category="security",
        owner_id=auth.subject_id,
        actor_id=auth.subject_id,
        actor_role=auth.role,
        ip_address=ip,
        user_agent=ua,
    )
    return TwoFactorSetupResponse(
        secret=secret,
        provisioning_uri=uri,
        qr_code_base64=qr,
        backup_codes=codes,
    )


@router.post("/2fa/verify", response_model=TwoFactorVerifyResponse)
async def verify_two_factor(
    payload: TwoFactorVerifyRequest,
    request: Request,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorVerifyResponse:
    manager = get_two_factor_manager()
    ok = await manager.verify(auth.subject_id, payload.code, db)
    ip, ua = _client_info(request)
    await get_audit_logger().log(
        db,
        action="2fa_verify",
        category="security",
        owner_id=auth.subject_id,
        actor_id=auth.subject_id,
        actor_role=auth.role,
        outcome="success" if ok else "failure",
        ip_address=ip,
        user_agent=ua,
    )
    return TwoFactorVerifyResponse(
        verified=ok,
        message="Two-factor authentication enabled" if ok else "Invalid code",
    )


@router.post("/2fa/disable", response_model=TwoFactorVerifyResponse)
async def disable_two_factor(
    payload: TwoFactorDisableRequest,
    request: Request,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorVerifyResponse:
    manager = get_two_factor_manager()
    ok = await manager.disable(auth.subject_id, payload.password, db)
    ip, ua = _client_info(request)
    await get_audit_logger().log(
        db,
        action="2fa_disabled",
        category="security",
        owner_id=auth.subject_id,
        actor_id=auth.subject_id,
        actor_role=auth.role,
        outcome="success" if ok else "failure",
        ip_address=ip,
        user_agent=ua,
    )
    return TwoFactorVerifyResponse(
        verified=ok,
        message="2FA disabled" if ok else "Password incorrect",
    )


@router.get("/2fa/status", response_model=TwoFactorStatusResponse)
async def get_two_factor_status(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> TwoFactorStatusResponse:
    manager = get_two_factor_manager()
    row = await manager.status(auth.subject_id, db)
    if row is None:
        return TwoFactorStatusResponse(
            enabled=False,
            confirmed_at=None,
            last_used_at=None,
            backup_codes_remaining=0,
        )

    backup_remaining = 0
    if row.backup_codes_encrypted:
        try:
            import json

            from app.services.security import get_encryption_manager

            codes_json = get_encryption_manager().decrypt_str(
                row.backup_codes_encrypted, aad=f"2fa-codes:{auth.subject_id}"
            )
            backup_remaining = len(json.loads(codes_json))
        except Exception:  # noqa: BLE001
            backup_remaining = 0

    return TwoFactorStatusResponse(
        enabled=row.enabled,
        confirmed_at=row.confirmed_at,
        last_used_at=row.last_used_at,
        backup_codes_remaining=backup_remaining,
    )


# ─── Data export ────────────────────────────────────────────


def _to_export_response(row, download_path: str | None = None) -> DataExportResponse:
    return DataExportResponse(
        export_id=row.id,
        status=row.status,
        archive_size_bytes=row.archive_size_bytes,
        archive_sha256=row.archive_sha256,
        download_url=download_path,
        expires_at=row.expires_at,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.post("/export", response_model=DataExportResponse)
async def create_data_export(
    request: Request,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> DataExportResponse:
    exporter = get_data_exporter()
    row = await exporter.create_export(auth.subject_id, db)

    ip, ua = _client_info(request)
    await get_audit_logger().log(
        db,
        action="data_export_created",
        category="data_access",
        owner_id=auth.subject_id,
        actor_id=auth.subject_id,
        actor_role=auth.role,
        resource_type="data_export",
        resource_id=row.id,
        outcome="success" if row.status == "ready" else "failure",
        ip_address=ip,
        user_agent=ua,
        details={"size_bytes": row.archive_size_bytes},
    )
    download = f"/api/security/export/{row.id}/download" if row.status == "ready" else None
    return _to_export_response(row, download)


@router.get("/export", response_model=DataExportListResponse)
async def list_data_exports(
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> DataExportListResponse:
    exporter = get_data_exporter()
    rows = await exporter.list_exports(auth.subject_id, db)
    return DataExportListResponse(
        exports=[
            _to_export_response(
                r,
                f"/api/security/export/{r.id}/download" if r.status == "ready" else None,
            )
            for r in rows
        ]
    )


@router.get("/export/{export_id}/download")
async def download_data_export(
    export_id: str,
    request: Request,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
):
    exporter = get_data_exporter()
    row = await exporter.get_export(export_id, auth.subject_id, db)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found")
    if row.status != "ready" or not row.archive_path:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Export not ready (status: {row.status})")

    archive = Path(row.archive_path)
    if not archive.exists():
        raise HTTPException(status.HTTP_410_GONE, "Archive missing on disk")

    await exporter.mark_downloaded(export_id, auth.subject_id, db)

    ip, ua = _client_info(request)
    await get_audit_logger().log(
        db,
        action="data_export_downloaded",
        category="data_access",
        owner_id=auth.subject_id,
        actor_id=auth.subject_id,
        actor_role=auth.role,
        resource_type="data_export",
        resource_id=export_id,
        ip_address=ip,
        user_agent=ua,
    )
    return FileResponse(
        path=str(archive),
        filename=archive.name,
        media_type="application/octet-stream",
    )


# ─── Account deletion ───────────────────────────────────────


@router.post("/delete-all", response_model=DataDeleteResponse)
async def delete_all_data(
    payload: DataDeleteRequest,
    request: Request,
    auth: AuthContext = Depends(require_role("owner")),
    db: AsyncSession = Depends(get_db),
) -> DataDeleteResponse:
    """Permanently delete the authenticated owner's account and all owned data.

    Requires confirm phrase, password, and TOTP code (if 2FA enabled).
    There is NO recovery from this operation.
    """
    destroyer = get_data_destroyer()
    ip, ua = _client_info(request)

    # Log the attempt BEFORE deletion (so we have a record even on success)
    await get_audit_logger().log(
        db,
        action="account_delete_attempted",
        category="security",
        owner_id=auth.subject_id,
        actor_id=auth.subject_id,
        actor_role=auth.role,
        ip_address=ip,
        user_agent=ua,
    )

    ok, message = await destroyer.delete_owner(
        owner_id=auth.subject_id,
        confirm_phrase=payload.confirm_phrase,
        password=payload.password,
        totp_code=payload.totp_code,
        db=db,
    )

    if not ok:
        # Log the failure (separate session-safe call since destroy may have rolled back)
        await get_audit_logger().log(
            db,
            action="account_delete_failed",
            category="security",
            owner_id=auth.subject_id,
            actor_id=auth.subject_id,
            actor_role=auth.role,
            outcome="failure",
            ip_address=ip,
            user_agent=ua,
            details={"reason": message},
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message)

    return DataDeleteResponse(
        deleted=True,
        message=message,
        deleted_at=datetime.now(UTC).replace(tzinfo=None),
    )
