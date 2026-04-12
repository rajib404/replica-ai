from datetime import datetime

from pydantic import BaseModel, Field


# ─── Audit log ─────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: str
    owner_id: str | None
    actor_id: str | None
    actor_role: str | None
    action: str
    category: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    details: dict | None
    created_at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


class AuditLogQuery(BaseModel):
    category: str | None = None
    action: str | None = None
    outcome: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


# ─── 2FA ────────────────────────────────────────────────────

class TwoFactorSetupResponse(BaseModel):
    secret: str  # base32-encoded TOTP secret (shown once)
    provisioning_uri: str  # otpauth://...
    qr_code_base64: str
    backup_codes: list[str]  # plaintext, shown once


class TwoFactorVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class TwoFactorVerifyResponse(BaseModel):
    verified: bool
    message: str


class TwoFactorStatusResponse(BaseModel):
    enabled: bool
    confirmed_at: datetime | None
    last_used_at: datetime | None
    backup_codes_remaining: int


class TwoFactorDisableRequest(BaseModel):
    password: str
    code: str | None = None  # optional TOTP for extra confirm


# ─── Encryption status ──────────────────────────────────────

class EncryptionStatusResponse(BaseModel):
    master_key_configured: bool
    algorithm: str  # "AES-256-GCM"
    kdf: str  # "PBKDF2-HMAC-SHA256"
    kdf_iterations: int
    encrypted_fields_count: int
    encrypted_files_count: int
    warning: str  # "If you lose your master key, your data is unrecoverable."


# ─── Data export & deletion ─────────────────────────────────

class DataExportResponse(BaseModel):
    export_id: str
    status: str  # pending|processing|ready|downloaded|expired|failed
    archive_size_bytes: int | None = None
    archive_sha256: str | None = None
    download_url: str | None = None
    expires_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DataExportListResponse(BaseModel):
    exports: list[DataExportResponse]


class DataDeleteRequest(BaseModel):
    """Two-step nuclear deletion. Both fields required."""
    confirm_phrase: str = Field(min_length=1)  # must equal settings.security_delete_confirm_phrase
    password: str = Field(min_length=1)
    totp_code: str | None = None  # required if 2FA enabled


class DataDeleteResponse(BaseModel):
    deleted: bool
    message: str
    deleted_at: datetime | None = None


# ─── Security headers report ────────────────────────────────

class SecurityHeadersStatus(BaseModel):
    csp_enabled: bool
    hsts_enabled: bool
    hsts_max_age: int
    x_frame_options: str
    x_content_type_options: str
    rate_limit_api_per_minute: int
    rate_limit_auth_per_minute: int
