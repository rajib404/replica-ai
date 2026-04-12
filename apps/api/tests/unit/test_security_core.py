"""Unit tests for ``app.core.security`` — JWT, hashing, Fernet encryption."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from jose import JWTError, jwt

from app.core import security


# ─── Password / secret hashing ──────────────────────────────


class TestHashSecret:
    def test_roundtrip(self) -> None:
        hashed = security.hash_secret("hunter2")
        assert hashed != "hunter2"
        assert security.verify_secret("hunter2", hashed) is True

    def test_wrong_password_rejected(self) -> None:
        hashed = security.hash_secret("correct")
        assert security.verify_secret("wrong", hashed) is False

    def test_different_hash_each_call(self) -> None:
        """bcrypt salts each hash — two hashes of the same input should differ."""
        h1 = security.hash_secret("same")
        h2 = security.hash_secret("same")
        assert h1 != h2
        # But both verify
        assert security.verify_secret("same", h1)
        assert security.verify_secret("same", h2)

    def test_bcrypt_format(self) -> None:
        hashed = security.hash_secret("x")
        # bcrypt hashes start with $2a$, $2b$, or $2y$
        assert hashed.startswith("$2")

    def test_unicode_password(self) -> None:
        password = "pässwörd🔑"
        h = security.hash_secret(password)
        assert security.verify_secret(password, h)


# ─── JWT tokens ─────────────────────────────────────────────


@pytest.fixture
def hs256_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch JWT to HS256 with a deterministic secret for testing."""
    monkeypatch.setattr(security.settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(security.settings, "jwt_secret_key", "test-secret-key-abc")
    monkeypatch.setattr(security.settings, "access_token_expire_minutes", 15)
    monkeypatch.setattr(security.settings, "refresh_token_expire_days", 7)
    monkeypatch.setattr(security.settings, "connect_token_expire_minutes", 5)


class TestAccessToken:
    def test_create_and_decode(self, hs256_settings: None) -> None:
        token = security.create_access_token("owner_123", "owner")
        payload = security.decode_token(token)
        assert payload["sub"] == "owner_123"
        assert payload["role"] == "owner"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_extra_claims_merged(self, hs256_settings: None) -> None:
        token = security.create_access_token(
            "owner_1", "family_member", extra={"rule_id": "r1", "access_level": "limited"}
        )
        payload = security.decode_token(token)
        assert payload["rule_id"] == "r1"
        assert payload["access_level"] == "limited"

    def test_tampered_token_rejected(self, hs256_settings: None) -> None:
        token = security.create_access_token("owner_1", "owner")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(JWTError):
            security.decode_token(tampered)

    def test_expired_token_rejected(
        self, hs256_settings: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Manually craft an expired token
        payload = {
            "sub": "o1",
            "role": "owner",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(
            payload, security.settings.jwt_secret_key, algorithm=security.settings.jwt_algorithm
        )
        with pytest.raises(JWTError):
            security.decode_token(token)

    def test_wrong_secret_rejected(self, hs256_settings: None) -> None:
        token = security.create_access_token("o1", "owner")
        other = jwt.encode(
            {"sub": "hacker"},
            "different-key",
            algorithm="HS256",
        )
        # Sanity: decoding with our secret should fail on the other token
        with pytest.raises(JWTError):
            security.decode_token(other)


class TestRefreshToken:
    def test_has_type_refresh(self, hs256_settings: None) -> None:
        token = security.create_refresh_token("o1", "owner")
        payload = security.decode_token(token)
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_refresh_jti_is_unique(self, hs256_settings: None) -> None:
        t1 = security.create_refresh_token("o1", "owner")
        t2 = security.create_refresh_token("o1", "owner")
        p1 = security.decode_token(t1)
        p2 = security.decode_token(t2)
        assert p1["jti"] != p2["jti"]


class TestConnectToken:
    def test_type_is_connect(self, hs256_settings: None) -> None:
        token = security.create_connect_token("owner_x")
        payload = security.decode_token(token)
        assert payload["type"] == "connect"
        assert payload["sub"] == "owner_x"


# ─── Fernet encrypt/decrypt ─────────────────────────────────


class TestFernetEncryption:
    def test_roundtrip(self) -> None:
        plain = "secret value"
        ct = security.encrypt_value(plain)
        assert ct != plain
        assert security.decrypt_value(ct) == plain

    def test_roundtrip_unicode(self) -> None:
        plain = "héllo wörld 🌍"
        ct = security.encrypt_value(plain)
        assert security.decrypt_value(ct) == plain

    def test_empty_string(self) -> None:
        ct = security.encrypt_value("")
        assert security.decrypt_value(ct) == ""

    def test_tampered_ciphertext_fails(self) -> None:
        from cryptography.fernet import InvalidToken

        ct = security.encrypt_value("secret")
        tampered = ct[:-4] + "AAAA"
        with pytest.raises(InvalidToken):
            security.decrypt_value(tampered)

    def test_two_encrypts_produce_different_ciphertexts(self) -> None:
        """Fernet uses a random IV per encryption."""
        c1 = security.encrypt_value("same input")
        c2 = security.encrypt_value("same input")
        assert c1 != c2
        assert security.decrypt_value(c1) == "same input"
        assert security.decrypt_value(c2) == "same input"
