"""Security utilities package."""

from .encryption import (
    DecryptionError,
    EncryptionError,
    decrypt_to_temp,
)
from .sqlcipher_support import (
    configure_connection,
    get_passphrase,
    cache_passphrase,
)

__all__ = [
    "DecryptionError",
    "EncryptionError",
    "decrypt_to_temp",
    "configure_connection",
    "get_passphrase",
    "cache_passphrase",
]
