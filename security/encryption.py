"""File encryption helpers for data at rest."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path

from health_records_collection import settings

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
            """Generate a new random key."""
            return base64.urlsafe_b64encode(os.urandom(32))

        def _keystream(self, *, length: int) -> bytes:
            """Generate a keystream of the requested length."""
            out = bytearray()
            counter = 0
            while len(out) < length:
                digest = hashlib.sha256(
                    self._key + counter.to_bytes(8, "little")
                ).digest()
                out.extend(digest)
                counter += 1
            return bytes(out[:length])

        def encrypt(self, in_data: bytes) -> bytes:
            """Encrypt data using backup XOR cipher."""
            stream = self._keystream(length=len(in_data))
            cipher = bytes(a ^ b for a, b in zip(in_data, stream))
            return base64.urlsafe_b64encode(cipher)

        def decrypt(self, token: bytes) -> bytes:
            """Decrypt data using backup XOR cipher."""
            decrypted_data = base64.urlsafe_b64decode(token)
            stream = self._keystream(length=len(decrypted_data))
            return bytes(a ^ b for a, b in zip(decrypted_data, stream))


logger = logging.getLogger(__name__)


class EncryptionManager:
    """Singleton encryption manager for file encryption/decryption."""

    _instance: EncryptionManager | None = None
    _key_path: Path | None = None

    def __new__(cls, key_path: Path | None = None) -> EncryptionManager:
        """Create or return the singleton instance.

        Args:
            key_path: Path where the encryption key is stored. Only used when creating
                     the first instance.

        Returns:
            EncryptionManager: The singleton encryption manager instance.

        Raises:
            ValueError: If no key_path is provided when creating the first instance.
        """
        if cls._instance is None:
            if key_path is None:
                raise ValueError("key_path is required when creating first instance")
            instance = super().__new__(cls)
            instance._initialize(key_path)
            cls._instance = instance
        return cls._instance

    def __init__(self, key_path: Path | None = None) -> None:
        """Initialize is called after __new__ but we do nothing here since
        initialization is handled in __new__ to ensure singleton pattern."""

    def _initialize(self, key_path: Path) -> None:
        """Initialize the instance with encryption key.

        Args:
            key_path: Path where the encryption key is stored.
        """
        self._key_path = key_path
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        """Load existing key or create a new one if none exists.

        Returns:
            bytes: The encryption key bytes.

        Raises:
            RuntimeError: If the key path is not set.
        """
        if self._key_path is None:
            raise RuntimeError("EncryptionManager not properly initialized")

        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = Fernet.generate_key()
        self._key_path.write_bytes(key)
        logger.info("Generated new encryption key at %s", self._key_path)
        return key

    def encrypt_bytes(self, encrypt_data: bytes) -> bytes:
        """Encrypt bytes and return the token."""
        return self._fernet.encrypt(encrypt_data)

    def decrypt_bytes(self, token: bytes) -> bytes:
        """Decrypt bytes from the token."""
        return self._fernet.decrypt(token)

    def encrypt_file(self, path: Path) -> Path:
        """Encrypt file contents and replace plaintext with .enc file."""
        path = path.resolve()
        read_data = path.read_bytes()
        encrypted = self.encrypt_bytes(read_data)
        secure_path = path.with_suffix(path.suffix + ".enc")
        secure_path.write_bytes(encrypted)
        path.unlink()
        logger.debug("Encrypted %s -> %s", path, secure_path)
        return secure_path

    def decrypt_to_temp(self, encrypted_path: Path) -> Path:
        """Decrypt an encrypted file into the user tmp directory."""
        encrypted_path = encrypted_path.resolve()
        plaintext = self.decrypt_bytes(encrypted_path.read_bytes())
        tmp_dir = Path(f"{settings.USER_SETTINGS_DIR} /tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        base_name = encrypted_path.stem  # removes only .enc
        suffix = "".join(encrypted_path.suffixes[:-1])
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix.count(".") > 1:
            # suffixes joined like '.xml.enc' -> suffix becomes '.xml.enc'
            suffix = "." + ".".join(encrypted_path.suffixes[:-1]).lstrip(".")
        if not suffix:
            suffix = ""
        hash_suffix = hashlib.sha256(str(encrypted_path).encode()).hexdigest()[:8]
        temp_name = f"{base_name}-{hash_suffix}{suffix}"
        temp_path = Path(f"{tmp_dir}/{temp_name}")
        temp_path.write_bytes(plaintext)
        return temp_path


def get_encryption_manager() -> EncryptionManager:
    """Get the singleton EncryptionManager instance.

    Returns:
        EncryptionManager: The singleton instance of the encryption manager.
    """
    key_path = Path(settings.USER_SETTINGS_DIR) / "encryption.key"
    return EncryptionManager(key_path)


def encrypt_to_temp(path: Path) -> Path:
    """Encrypt the specified file and return the path to the encrypted file."""
    return get_encryption_manager().encrypt_file(path)


def decrypt_to_temp(path: Path) -> Path:
    """Decrypt the specified encrypted file to a temporary location."""
    return get_encryption_manager().decrypt_to_temp(path)
