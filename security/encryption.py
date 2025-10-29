"""File encryption helpers for data at rest."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - depends on optional dependency
    logging.getLogger(__name__).warning(
        "cryptography not installed; falling back to XOR-based cipher"
    )

    class Fernet:  # type: ignore
        """Very small XOR-based fallback (not production-grade)."""

        def __init__(self, key: bytes) -> None:
            self._key = key

        @staticmethod
        def generate_key() -> bytes:
            return base64.urlsafe_b64encode(os.urandom(32))

        def _keystream(self, *, length: int) -> bytes:
            out = bytearray()
            counter = 0
            while len(out) < length:
                digest = hashlib.sha256(self._key + counter.to_bytes(8, "little")).digest()
                out.extend(digest)
                counter += 1
            return bytes(out[:length])

        def encrypt(self, data: bytes) -> bytes:
            stream = self._keystream(length=len(data))
            cipher = bytes(a ^ b for a, b in zip(data, stream))
            return base64.urlsafe_b64encode(cipher)

        def decrypt(self, token: bytes) -> bytes:
            data = base64.urlsafe_b64decode(token)
            stream = self._keystream(length=len(data))
            return bytes(a ^ b for a, b in zip(data, stream))



logger = logging.getLogger(__name__)

_MANAGER: "EncryptionManager" | None = None


class EncryptionManager:
    """Manage symmetric encryption of files using Fernet (AES-128)."""

    def __init__(self, key_path: Path) -> None:
        self._key_path = key_path
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = Fernet.generate_key()
        self._key_path.write_bytes(key)
        logger.info("Generated new encryption key at %s", self._key_path)
        return key

    def encrypt_bytes(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)

    def encrypt_file(self, path: Path) -> Path:
        """Encrypt file contents and replace plaintext with .enc file."""
        path = path.resolve()
        data = path.read_bytes()
        encrypted = self.encrypt_bytes(data)
        secure_path = path.with_suffix(path.suffix + '.enc')
        secure_path.write_bytes(encrypted)
        path.unlink()
        logger.debug("Encrypted %s -> %s", path, secure_path)
        return secure_path

    def decrypt_to_temp(self, encrypted_path: Path) -> Path:
        """Decrypt an encrypted file into the user tmp directory."""
        encrypted_path = encrypted_path.resolve()
        plaintext = self.decrypt_bytes(encrypted_path.read_bytes())
        from importlib import import_module
        settings = import_module("settings")
        tmp_dir = settings.USER_SETTINGS_DIR / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        base_name = encrypted_path.stem  # removes only .enc
        suffix = ''.join(encrypted_path.suffixes[:-1])
        if suffix and not suffix.startswith('.'):
            suffix = f'.{suffix}'
        if suffix.count('.') > 1:
            # suffixes joined like '.xml.enc' -> suffix becomes '.xml.enc'
            suffix = '.' + '.'.join(encrypted_path.suffixes[:-1]).lstrip('.')
        if not suffix:
            suffix = ''
        temp_name = f"{base_name}-{hashlib.sha256(str(encrypted_path).encode()).hexdigest()[:8]}{suffix}"
        temp_path = tmp_dir / temp_name
        temp_path.write_bytes(plaintext)
        return temp_path


def get_encryption_manager() -> EncryptionManager:
    global _MANAGER
    if _MANAGER is None:
        from importlib import import_module

        settings = import_module("settings")
        key_path = settings.USER_SETTINGS_DIR / "encryption.key"
        _MANAGER = EncryptionManager(key_path)
    return _MANAGER


def encrypt_file(path: Path) -> Path:
    return get_encryption_manager().encrypt_file(path)


def decrypt_to_temp(path: Path) -> Path:
    return get_encryption_manager().decrypt_to_temp(path)
