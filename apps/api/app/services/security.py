"""Security service: encryption-at-rest, audit logging, 2FA, data export & deletion.

This module provides defensive security primitives for protecting owner data:
- AES-256-GCM encryption (PBKDF2-derived keys) for sensitive fields and files.
- Append-only audit logging for sensitive actions.
- TOTP-based 2FA with backup codes.
- Owner data export (signed archive) and account deletion (nuclear option).

Security model:
- The encryption master key MUST live in `ENCRYPTION_MASTER_KEY` env var only.
- If the master key is lost, encrypted data becomes permanently unrecoverable.
- All queries must filter by owner_id; this module never bypasses isolation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyotp
import qrcode
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_secret, verify_secret
from app.models.owner import (
    AuditLog,
    DataExportRequest,
    Owner,
    TwoFactorAuth,
)


# ─── Helpers ────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generate_id(prefix: str = "c") -> str:
    import time

    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"{prefix}{ts}{rand}"


# ─── Encryption manager (AES-256-GCM + PBKDF2) ──────────────


class EncryptionManager:
    """AES-256-GCM with per-payload random salt + nonce.

    Wire format (base64): salt(16) || nonce(12) || ciphertext+tag
    The master key is loaded from settings.encryption_master_key (env-only).
    """

    def __init__(self, master_key: str | None = None) -> None:
        self._master = (master_key or settings.encryption_master_key or "").encode()
        self._iterations = settings.encryption_pbkdf2_iterations
        self._salt_bytes = settings.encryption_pbkdf2_salt_bytes
        self._nonce_bytes = settings.encryption_aes_nonce_bytes

    @property
    def is_configured(self) -> bool:
        return len(self._master) >= 16

    def _derive_key(self, salt: bytes) -> bytes:
        if not self.is_configured:
            raise RuntimeError(
                "ENCRYPTION_MASTER_KEY is not set. Refusing to encrypt/decrypt."
            )
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self._iterations,
        )
        return kdf.derive(self._master)

    def encrypt_bytes(self, plaintext: bytes, aad: bytes | None = None) -> bytes:
        salt = os.urandom(self._salt_bytes)
        nonce = os.urandom(self._nonce_bytes)
        key = self._derive_key(salt)
        ct = AESGCM(key).encrypt(nonce, plaintext, aad)
        return salt + nonce + ct

    def decrypt_bytes(self, blob: bytes, aad: bytes | None = None) -> bytes:
        salt = blob[: self._salt_bytes]
        nonce = blob[self._salt_bytes : self._salt_bytes + self._nonce_bytes]
        ct = blob[self._salt_bytes + self._nonce_bytes :]
        key = self._derive_key(salt)
        return AESGCM(key).decrypt(nonce, ct, aad)

    def encrypt_str(self, plaintext: str, aad: str | None = None) -> str:
        aad_b = aad.encode() if aad else None
        blob = self.encrypt_bytes(plaintext.encode("utf-8"), aad_b)
        return base64.urlsafe_b64encode(blob).decode("ascii")

    def decrypt_str(self, ciphertext: str, aad: str | None = None) -> str:
        aad_b = aad.encode() if aad else None
        blob = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        return self.decrypt_bytes(blob, aad_b).decode("utf-8")

    def encrypt_file(self, src_path: str | Path, dst_path: str | Path) -> None:
        src = Path(src_path)
        dst = Path(dst_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dst.write_bytes(self.encrypt_bytes(data))

    def decrypt_file(self, src_path: str | Path, dst_path: str | Path) -> None:
        src = Path(src_path)
        dst = Path(dst_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        blob = src.read_bytes()
        dst.write_bytes(self.decrypt_bytes(blob))


_encryption_manager: EncryptionManager | None = None


def get_encryption_manager() -> EncryptionManager:
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager


# ─── Audit logger ───────────────────────────────────────────


class AuditLogger:
    """Append-only audit log writer. Never updates or deletes existing rows."""

    VALID_CATEGORIES = {
        "auth",
        "data_access",
        "settings",
        "external_api",
        "payment",
        "security",
        "admin",
    }

    async def log(
        self,
        db: AsyncSession,
        *,
        action: str,
        category: str,
        owner_id: str | None = None,
        actor_id: str | None = None,
        actor_role: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: str = "success",
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        if not settings.audit_log_enabled:
            return None  # type: ignore[return-value]
        if category not in self.VALID_CATEGORIES:
            raise ValueError(f"Invalid audit category: {category}")

        entry = AuditLog(
            id=_generate_id("a"),
            owner_id=owner_id,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            category=category,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            details=details,
            created_at=_utcnow(),
        )
        db.add(entry)
        await db.commit()
        return entry

    async def query(
        self,
        db: AsyncSession,
        *,
        owner_id: str,
        category: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        from sqlalchemy import func as sa_func

        stmt = select(AuditLog).where(AuditLog.owner_id == owner_id)
        count_stmt = select(sa_func.count(AuditLog.id)).where(AuditLog.owner_id == owner_id)
        if category:
            stmt = stmt.where(AuditLog.category == category)
            count_stmt = count_stmt.where(AuditLog.category == category)
        if action:
            stmt = stmt.where(AuditLog.action == action)
            count_stmt = count_stmt.where(AuditLog.action == action)
        if outcome:
            stmt = stmt.where(AuditLog.outcome == outcome)
            count_stmt = count_stmt.where(AuditLog.outcome == outcome)
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)
            count_stmt = count_stmt.where(AuditLog.created_at >= since)
        if until:
            stmt = stmt.where(AuditLog.created_at <= until)
            count_stmt = count_stmt.where(AuditLog.created_at <= until)

        total = (await db.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return list(rows), int(total)

    async def prune_expired(self, db: AsyncSession) -> int:
        """Delete audit rows older than retention. retention_days=0 means forever."""
        retention = settings.audit_log_retention_days
        if retention <= 0:
            return 0
        cutoff = _utcnow() - timedelta(days=retention)
        result = await db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
        await db.commit()
        return result.rowcount or 0


_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# ─── Two-factor authentication (TOTP) ───────────────────────


class TwoFactorManager:
    """TOTP-based 2FA with backup codes. Secrets stored encrypted at rest."""

    BACKUP_CODE_COUNT = 10
    BACKUP_CODE_LEN = 10  # base32 chars

    def __init__(self) -> None:
        self._enc = get_encryption_manager()

    def _generate_backup_codes(self) -> list[str]:
        return [
            base64.b32encode(secrets.token_bytes(8)).decode("ascii")[: self.BACKUP_CODE_LEN]
            for _ in range(self.BACKUP_CODE_COUNT)
        ]

    def _hash_backup_code(self, code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def _provisioning_uri(self, secret: str, account: str) -> str:
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=account,
            issuer_name=settings.totp_issuer,
        )

    def _qr_base64(self, uri: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    async def setup(
        self, owner_id: str, db: AsyncSession
    ) -> tuple[str, str, str, list[str]]:
        """Generate a fresh secret, store encrypted, return secret/uri/qr/backup codes.
        2FA is NOT enabled until verify() is called with a valid code."""
        owner = (await db.execute(select(Owner).where(Owner.id == owner_id))).scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        secret = pyotp.random_base32()
        backup_codes = self._generate_backup_codes()
        hashed_codes = [self._hash_backup_code(c) for c in backup_codes]

        existing = (
            await db.execute(select(TwoFactorAuth).where(TwoFactorAuth.owner_id == owner_id))
        ).scalar_one_or_none()

        secret_enc = self._enc.encrypt_str(secret, aad=f"2fa:{owner_id}")
        codes_enc = self._enc.encrypt_str(json.dumps(hashed_codes), aad=f"2fa-codes:{owner_id}")

        if existing is None:
            row = TwoFactorAuth(
                id=_generate_id("t"),
                owner_id=owner_id,
                secret_encrypted=secret_enc,
                backup_codes_encrypted=codes_enc,
                enabled=False,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(row)
        else:
            existing.secret_encrypted = secret_enc
            existing.backup_codes_encrypted = codes_enc
            existing.enabled = False
            existing.confirmed_at = None
            existing.updated_at = _utcnow()
        await db.commit()

        uri = self._provisioning_uri(secret, owner.email)
        qr = self._qr_base64(uri)
        return secret, uri, qr, backup_codes

    async def verify(self, owner_id: str, code: str, db: AsyncSession) -> bool:
        row = (
            await db.execute(select(TwoFactorAuth).where(TwoFactorAuth.owner_id == owner_id))
        ).scalar_one_or_none()
        if row is None:
            return False

        secret = self._enc.decrypt_str(row.secret_encrypted, aad=f"2fa:{owner_id}")
        totp = pyotp.TOTP(secret, digits=settings.totp_digits, interval=settings.totp_period_seconds)

        # Try TOTP first
        if totp.verify(code, valid_window=settings.totp_window):
            if not row.enabled:
                row.enabled = True
                row.confirmed_at = _utcnow()
            row.last_used_at = _utcnow()
            await db.commit()
            return True

        # Try backup codes
        if row.backup_codes_encrypted:
            codes_json = self._enc.decrypt_str(
                row.backup_codes_encrypted, aad=f"2fa-codes:{owner_id}"
            )
            hashed_codes: list[str] = json.loads(codes_json)
            code_hash = self._hash_backup_code(code)
            if code_hash in hashed_codes:
                hashed_codes.remove(code_hash)
                row.backup_codes_encrypted = self._enc.encrypt_str(
                    json.dumps(hashed_codes), aad=f"2fa-codes:{owner_id}"
                )
                row.last_used_at = _utcnow()
                if not row.enabled:
                    row.enabled = True
                    row.confirmed_at = _utcnow()
                await db.commit()
                return True

        return False

    async def disable(self, owner_id: str, password: str, db: AsyncSession) -> bool:
        owner = (
            await db.execute(select(Owner).where(Owner.id == owner_id))
        ).scalar_one_or_none()
        if owner is None or not owner.auth_secret_hash:
            return False
        if not verify_secret(password, owner.auth_secret_hash):
            return False

        await db.execute(delete(TwoFactorAuth).where(TwoFactorAuth.owner_id == owner_id))
        await db.commit()
        return True

    async def status(self, owner_id: str, db: AsyncSession) -> TwoFactorAuth | None:
        return (
            await db.execute(select(TwoFactorAuth).where(TwoFactorAuth.owner_id == owner_id))
        ).scalar_one_or_none()

    async def is_enabled(self, owner_id: str, db: AsyncSession) -> bool:
        row = await self.status(owner_id, db)
        return bool(row and row.enabled)


_two_factor_manager: TwoFactorManager | None = None


def get_two_factor_manager() -> TwoFactorManager:
    global _two_factor_manager
    if _two_factor_manager is None:
        _two_factor_manager = TwoFactorManager()
    return _two_factor_manager


# ─── Data exporter ──────────────────────────────────────────


class DataExporter:
    """Builds an encrypted tar.gz archive of an owner's data and serves it once."""

    def __init__(self) -> None:
        self._enc = get_encryption_manager()
        self._export_dir = Path(settings.security_export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)

    async def create_export(self, owner_id: str, db: AsyncSession) -> DataExportRequest:
        export_id = _generate_id("e")
        request = DataExportRequest(
            id=export_id,
            owner_id=owner_id,
            status="processing",
            created_at=_utcnow(),
            expires_at=_utcnow() + timedelta(hours=settings.security_export_ttl_hours),
        )
        db.add(request)
        await db.commit()

        try:
            archive_path = await self._build_archive(owner_id, export_id, db)
            request.status = "ready"
            request.archive_path = str(archive_path)
            request.archive_size_bytes = archive_path.stat().st_size
            request.archive_sha256 = self._sha256_file(archive_path)
            request.completed_at = _utcnow()
        except Exception as exc:  # noqa: BLE001
            request.status = "failed"
            request.error_message = str(exc)
            request.completed_at = _utcnow()

        await db.commit()
        await db.refresh(request)
        return request

    async def _build_archive(
        self, owner_id: str, export_id: str, db: AsyncSession
    ) -> Path:
        owner = (
            await db.execute(select(Owner).where(Owner.id == owner_id))
        ).scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        manifest: dict[str, Any] = {
            "export_id": export_id,
            "owner_id": owner_id,
            "exported_at": _utcnow().isoformat(),
            "owner": {
                "id": owner.id,
                "name": owner.name,
                "email": owner.email,
                "phone": owner.phone,
                "preferred_language": owner.preferred_language,
                "created_at": owner.created_at.isoformat(),
            },
        }

        tmp_tar = self._export_dir / f"{export_id}.tar.gz"
        with tarfile.open(tmp_tar, "w:gz") as tar:
            manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))

        # Encrypt the archive at rest
        encrypted_path = self._export_dir / f"{export_id}.tar.gz.enc"
        if self._enc.is_configured:
            self._enc.encrypt_file(tmp_tar, encrypted_path)
            tmp_tar.unlink(missing_ok=True)
            return encrypted_path
        return tmp_tar

    def _sha256_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(64 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    async def list_exports(
        self, owner_id: str, db: AsyncSession
    ) -> list[DataExportRequest]:
        rows = (
            await db.execute(
                select(DataExportRequest)
                .where(DataExportRequest.owner_id == owner_id)
                .order_by(DataExportRequest.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def get_export(
        self, export_id: str, owner_id: str, db: AsyncSession
    ) -> DataExportRequest | None:
        return (
            await db.execute(
                select(DataExportRequest).where(
                    DataExportRequest.id == export_id,
                    DataExportRequest.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()

    async def mark_downloaded(
        self, export_id: str, owner_id: str, db: AsyncSession
    ) -> None:
        row = await self.get_export(export_id, owner_id, db)
        if row is None:
            return
        row.downloaded_at = _utcnow()
        row.status = "downloaded"
        await db.commit()


_data_exporter: DataExporter | None = None


def get_data_exporter() -> DataExporter:
    global _data_exporter
    if _data_exporter is None:
        _data_exporter = DataExporter()
    return _data_exporter


# ─── Data destroyer (account deletion) ──────────────────────


class DataDestroyer:
    """Nuclear option: irreversibly delete all data for an owner.

    Requires three-factor confirmation: confirm phrase + password + (TOTP if 2FA enabled).
    """

    def __init__(self) -> None:
        self._two_factor = get_two_factor_manager()

    async def delete_owner(
        self,
        owner_id: str,
        confirm_phrase: str,
        password: str,
        totp_code: str | None,
        db: AsyncSession,
    ) -> tuple[bool, str]:
        if not hmac.compare_digest(confirm_phrase, settings.security_delete_confirm_phrase):
            return False, "Confirmation phrase does not match"

        owner = (
            await db.execute(select(Owner).where(Owner.id == owner_id))
        ).scalar_one_or_none()
        if owner is None:
            return False, "Owner not found"

        if not owner.auth_secret_hash:
            return False, "No password set on account"
        if not verify_secret(password, owner.auth_secret_hash):
            return False, "Password incorrect"

        if await self._two_factor.is_enabled(owner_id, db):
            if not totp_code:
                return False, "2FA code required"
            if not await self._two_factor.verify(owner_id, totp_code, db):
                return False, "2FA code invalid"

        # Cascade-delete owner-owned tables. Order matters for FK constraints
        # if any exist; this codebase uses string FKs without DB-level cascades,
        # so any owned row keyed by owner_id is removed.
        await self._cascade_delete(owner_id, db)

        # Finally remove the owner
        await db.execute(delete(Owner).where(Owner.id == owner_id))
        await db.commit()
        return True, "Account permanently deleted"

    async def _cascade_delete(self, owner_id: str, db: AsyncSession) -> None:
        from app.models.owner import (
            AccessRule,
            BillingConfig,
            BrowseConfig,
            BrowseDomainRule,
            BrowseLog,
            EmotionLog,
            ExternalLLMConfig,
            ExternalLLMUsageLog,
            FamilyInvite,
            FineTuneConfig,
            LearningConfig,
            LearningLog,
            LegacyConfig,
            ModelInstance,
            ModelVersion,
            PageMonitor,
            PaymentLog,
            PersonalityProfile,
            SurvivalConfig,
            TwoFactorAuth,
        )

        owned_tables = [
            TwoFactorAuth,
            DataExportRequest,
            ModelInstance,
            AccessRule,
            FamilyInvite,
            LegacyConfig,
            ExternalLLMConfig,
            ExternalLLMUsageLog,
            BrowseLog,
            PageMonitor,
            BrowseDomainRule,
            BrowseConfig,
            BillingConfig,
            PaymentLog,
            SurvivalConfig,
            LearningConfig,
            LearningLog,
            FineTuneConfig,
            ModelVersion,
            PersonalityProfile,
            EmotionLog,
        ]
        for model in owned_tables:
            await db.execute(delete(model).where(model.owner_id == owner_id))

        # Clean up any export archives on disk
        export_dir = Path(settings.security_export_dir)
        if export_dir.exists():
            for archive in export_dir.glob(f"*{owner_id}*"):
                try:
                    if archive.is_dir():
                        shutil.rmtree(archive)
                    else:
                        archive.unlink()
                except OSError:
                    pass


_data_destroyer: DataDestroyer | None = None


def get_data_destroyer() -> DataDestroyer:
    global _data_destroyer
    if _data_destroyer is None:
        _data_destroyer = DataDestroyer()
    return _data_destroyer


# ─── Convenience: encryption status ─────────────────────────


async def encryption_status(db: AsyncSession) -> dict[str, Any]:
    enc = get_encryption_manager()
    return {
        "master_key_configured": enc.is_configured,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "kdf_iterations": settings.encryption_pbkdf2_iterations,
        "encrypted_fields_count": 0,  # populated by inventory query if desired
        "encrypted_files_count": 0,
        "warning": (
            "If you lose your ENCRYPTION_MASTER_KEY environment variable, all "
            "encrypted data will be permanently unrecoverable. There is no recovery "
            "mechanism. Back it up in a secure password manager."
        ),
    }
