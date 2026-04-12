import base64
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from cryptography.fernet import Fernet
from jose import jwt

from app.core.config import settings


# ─── Password / secret hashing ───────────────────────────

def hash_secret(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_secret(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── JWT tokens ───────────────────────────────────────────

def create_access_token(subject: str, role: str, extra: dict | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_connect_token(owner_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": owner_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.connect_token_expire_minutes),
        "type": "connect",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ─── Symmetric encryption (Fernet) ──────────────────────

def _get_fernet() -> Fernet:
    key = settings.encryption_key.encode()
    # Pad/derive a valid 32-byte Fernet key from the config value
    raw = base64.urlsafe_b64decode(key + b"==")[:32] if len(key) > 32 else key.ljust(32, b"0")
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_value(plain: str) -> str:
    """Encrypt a string value using Fernet symmetric encryption."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted string value."""
    return _get_fernet().decrypt(encrypted.encode()).decode()
