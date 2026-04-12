"""Unit tests for the AES-256-GCM EncryptionManager.

These tests exercise the cryptographic primitives in isolation without
touching the database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from app.services.security import EncryptionManager


@pytest.fixture
def enc() -> EncryptionManager:
    """A fully-configured EncryptionManager with a deterministic key."""
    return EncryptionManager(
        master_key="test-master-key-with-enough-entropy-1234567890"
    )


@pytest.fixture
def weak_enc() -> EncryptionManager:
    """An un-configured manager (master key too short)."""
    return EncryptionManager(master_key="too-short")


class TestIsConfigured:
    def test_configured_when_master_key_is_long_enough(
        self, enc: EncryptionManager
    ) -> None:
        assert enc.is_configured is True

    def test_not_configured_when_master_key_too_short(
        self, weak_enc: EncryptionManager
    ) -> None:
        assert weak_enc.is_configured is False

    def test_refuses_to_encrypt_when_not_configured(
        self, weak_enc: EncryptionManager
    ) -> None:
        with pytest.raises(RuntimeError, match="ENCRYPTION_MASTER_KEY"):
            weak_enc.encrypt_bytes(b"data")


class TestEncryptDecryptBytes:
    def test_roundtrip(self, enc: EncryptionManager) -> None:
        plain = b"secret bytes"
        ct = enc.encrypt_bytes(plain)
        assert ct != plain
        assert enc.decrypt_bytes(ct) == plain

    def test_roundtrip_empty(self, enc: EncryptionManager) -> None:
        assert enc.decrypt_bytes(enc.encrypt_bytes(b"")) == b""

    def test_roundtrip_large(self, enc: EncryptionManager) -> None:
        plain = b"A" * (1024 * 1024)  # 1 MB
        assert enc.decrypt_bytes(enc.encrypt_bytes(plain)) == plain

    def test_two_encryptions_produce_different_ciphertexts(
        self, enc: EncryptionManager
    ) -> None:
        """Random salt + nonce per call → different ciphertexts."""
        c1 = enc.encrypt_bytes(b"same")
        c2 = enc.encrypt_bytes(b"same")
        assert c1 != c2
        assert enc.decrypt_bytes(c1) == b"same"
        assert enc.decrypt_bytes(c2) == b"same"

    def test_ciphertext_prefix_is_salt_plus_nonce(
        self, enc: EncryptionManager
    ) -> None:
        """Wire format: salt(16) || nonce(12) || ciphertext+tag"""
        ct = enc.encrypt_bytes(b"hello")
        # Header should be 16 + 12 = 28 bytes, plus the ciphertext/tag.
        assert len(ct) > 28
        # The salt portion should look random (not all zero).
        assert ct[:16] != b"\x00" * 16

    def test_tampered_ciphertext_fails_with_invalid_tag(
        self, enc: EncryptionManager
    ) -> None:
        ct = enc.encrypt_bytes(b"hello world")
        tampered = ct[:-1] + bytes([ct[-1] ^ 0x01])
        with pytest.raises(InvalidTag):
            enc.decrypt_bytes(tampered)

    def test_wrong_key_fails(self) -> None:
        a = EncryptionManager(master_key="key-a-with-enough-entropy-111111111111")
        b = EncryptionManager(master_key="key-b-with-enough-entropy-222222222222")
        ct = a.encrypt_bytes(b"data")
        with pytest.raises(InvalidTag):
            b.decrypt_bytes(ct)


class TestAAD:
    def test_aad_roundtrip(self, enc: EncryptionManager) -> None:
        ct = enc.encrypt_bytes(b"data", aad=b"context")
        assert enc.decrypt_bytes(ct, aad=b"context") == b"data"

    def test_wrong_aad_fails(self, enc: EncryptionManager) -> None:
        ct = enc.encrypt_bytes(b"data", aad=b"context-a")
        with pytest.raises(InvalidTag):
            enc.decrypt_bytes(ct, aad=b"context-b")

    def test_missing_aad_on_decrypt_fails(self, enc: EncryptionManager) -> None:
        ct = enc.encrypt_bytes(b"data", aad=b"context")
        with pytest.raises(InvalidTag):
            enc.decrypt_bytes(ct, aad=None)


class TestEncryptDecryptStr:
    def test_roundtrip(self, enc: EncryptionManager) -> None:
        ct = enc.encrypt_str("hello")
        assert isinstance(ct, str)
        assert enc.decrypt_str(ct) == "hello"

    def test_roundtrip_unicode(self, enc: EncryptionManager) -> None:
        text = "héllo 🔑 wörld"
        assert enc.decrypt_str(enc.encrypt_str(text)) == text

    def test_with_aad(self, enc: EncryptionManager) -> None:
        ct = enc.encrypt_str("secret", aad="owner_123")
        assert enc.decrypt_str(ct, aad="owner_123") == "secret"
        with pytest.raises(InvalidTag):
            enc.decrypt_str(ct, aad="other_owner")

    def test_output_is_urlsafe_base64(self, enc: EncryptionManager) -> None:
        import base64

        ct = enc.encrypt_str("x")
        # Should decode cleanly as urlsafe base64
        decoded = base64.urlsafe_b64decode(ct)
        assert len(decoded) > 0


class TestEncryptDecryptFile:
    def test_roundtrip(self, enc: EncryptionManager, tmp_path: Path) -> None:
        src = tmp_path / "plain.txt"
        enc_path = tmp_path / "plain.enc"
        dec_path = tmp_path / "decoded.txt"

        src.write_bytes(b"file contents")

        enc.encrypt_file(src, enc_path)
        assert enc_path.exists()
        assert enc_path.read_bytes() != src.read_bytes()

        enc.decrypt_file(enc_path, dec_path)
        assert dec_path.read_bytes() == b"file contents"

    def test_creates_parent_directory(
        self, enc: EncryptionManager, tmp_path: Path
    ) -> None:
        src = tmp_path / "plain.bin"
        dst = tmp_path / "nested" / "dir" / "plain.enc"
        src.write_bytes(b"data")

        enc.encrypt_file(src, dst)
        assert dst.exists()

    def test_binary_roundtrip(
        self, enc: EncryptionManager, tmp_path: Path
    ) -> None:
        """Encryption must be binary-safe."""
        src = tmp_path / "bin.dat"
        out = tmp_path / "bin.out"
        content = bytes(range(256)) * 64  # every byte value

        src.write_bytes(content)
        enc_path = tmp_path / "bin.enc"
        enc.encrypt_file(src, enc_path)
        enc.decrypt_file(enc_path, out)
        assert out.read_bytes() == content
