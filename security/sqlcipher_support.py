# Purpose: Manage SQLCipher passphrases and harden connection settings.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: tests/test_db_utils.py
# AI-assisted: Module created with AI assistance.
"""Helpers for acquiring SQLCipher credentials and applying secure pragmas."""

from __future__ import annotations

import logging
import os
import sqlite3
from getpass import getpass
from typing import Optional

PASSPHRASE_ENV = "HRC_SQLCIPHER_PASSPHRASE"  # nosec B105
_PASSPHRASE_CACHE: Optional[str] = None

logger = logging.getLogger(__name__)


def _validate_passphrase(value: str) -> str:
    """Ensure the provided passphrase is non-empty."""
    if not value or not value.strip():
        raise RuntimeError("SQLCipher passphrase must not be empty.")
    return value


def cache_passphrase(value: str) -> str:
    """
    Persist a validated passphrase in memory for subsequent requests.

    Args:
        value: Secret string supplied by the caller.

    Returns:
        The normalised passphrase that was cached.
    """
    global _PASSPHRASE_CACHE  # pylint: disable=global-statement
    _PASSPHRASE_CACHE = _validate_passphrase(value)
    logger.debug("SQLCipher passphrase cached in memory.")
    return _PASSPHRASE_CACHE


def get_passphrase(*, prompt: bool = False) -> str:
    """
    Retrieve the SQLCipher passphrase from cache, env var, or interactive input.

    Args:
        prompt: When True, fall back to an interactive prompt if no environment
            variable is present. Defaults to False so headless deployments fail
            fast rather than hanging.

    Returns:
        The passphrase string cached for subsequent calls.
    """
    # pylint: disable=useless-suppression
    # pylint: disable=global-statement,global-variable-not-assigned
    global _PASSPHRASE_CACHE
    if _PASSPHRASE_CACHE:
        return _PASSPHRASE_CACHE

    env_value = os.getenv(PASSPHRASE_ENV)
    if env_value:
        return cache_passphrase(env_value)

    if prompt:
        passphrase = getpass("Enter SQLCipher database passphrase: ")
        return cache_passphrase(passphrase)

    raise RuntimeError(
        "SQLCipher passphrase is unavailable. Set the "
        f"{PASSPHRASE_ENV} environment variable or call get_passphrase(prompt=True)."
    )


def configure_connection(conn: sqlite3.Connection, passphrase: str) -> None:
    """
    Apply the SQLCipher key and hardening pragmas to a DB-API connection.

    Args:
        conn: An SQLCipher DB-API connection object.
        passphrase: Secret used to unlock the encrypted database.
    """
    _validate_passphrase(passphrase)

    # sqlcipher3-wheels does not support bound parameters for PRAGMA key, so we
    # safely inline the passphrase after escaping single quotes.
    escaped = passphrase.replace("'", "''")
    conn.execute(f"PRAGMA key = '{escaped}';")
    # Harden key derivation and page settings to current recommendations.
    conn.execute("PRAGMA cipher_page_size = 4096;")
    conn.execute("PRAGMA kdf_iter = 256000;")
    conn.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512;")
    conn.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;")
    if os.name != "nt":
        conn.execute("PRAGMA cipher_memory_security = ON;")
    else:
        logger.debug(
            "Skipping PRAGMA cipher_memory_security on Windows platforms lacking "
            "Lock Pages in Memory privilege."
        )

    # Enforce referential integrity and durable journaling.
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;").fetchone()


def clear_cached_passphrase() -> None:
    """Erase the cached passphrase (useful for tests)."""
    global _PASSPHRASE_CACHE  # pylint: disable=global-statement
    _PASSPHRASE_CACHE = None
