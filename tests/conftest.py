import hashlib
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Any, Iterator

import pytest
from health_records_collection.db.schema import ensure_schema
from health_records_collection.services import providers as provider_service


@pytest.fixture
def schema_conn() -> Iterator[sqlite3.Connection]:
    """Provide an in-memory SQLite connection seeded with the project schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_sql = Path("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    ensure_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def data_source_id(test_schema_conn: sqlite3.Connection) -> int:
    """Insert a reusable data_source row for tests that need a valid foreign key."""
    cursor = test_schema_conn.cursor()
    archive_hash = hashlib.sha256(b"archive.zip").hexdigest()
    cursor.execute(
        """
        INSERT INTO ingested_archive (
            archive_name,
            archive_sha256,
            first_ingested_at,
            last_ingested_at,
            ingest_count
        ) VALUES (?, ?, '2025-10-12T00:00:00Z', '2025-10-12T00:00:00Z', 1)
        """,
        ("archive.zip", archive_hash),
    )
    archive_id = int(cursor.lastrowid) if cursor.lastrowid is not None else 0
    cursor.execute(
        """
        INSERT INTO data_source (
            original_filename,
            ingested_at,
            file_sha256,
            source_archive_id
        ) VALUES (?, ?, ?, ?)
        """,
        ("sample.xml", "2025-10-12T00:00:00Z", "hash-sample", archive_id),
    )
    test_schema_conn.commit()
    return int(cursor.lastrowid) if cursor.lastrowid is not None else 0


@pytest.fixture(autouse=True)
def clear_provider_cache() -> None:
    """Reset provider cache between tests to avoid cross-connection leakage."""
    # pylint: disable=protected-access
    # Direct cache access needed for test isolation
    provider_service._PROVIDER_CACHE.clear()


def _get_test_modules() -> tuple[Any, Any, Any]:
    """Get the modules needed for test isolation.

    Returns:
        tuple: Settings, encryption, and sqlcipher support modules
    """
    return (
        import_module("settings"),
        import_module("security.encryption"),
        import_module("security.sqlcipher_support"),
    )


@pytest.fixture(autouse=True)
def isolate_user_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Ensure user settings and encryption artifacts use a temp directory for tests."""
    settings_mod, encryption_mod, sqlcipher_mod = _get_test_modules()

    # Create isolated directories for settings and encryption
    settings_dir = tmp_path_factory.mktemp("settings")
    encryption_dir = tmp_path_factory.mktemp("encryption")

    # Update settings paths
    monkeypatch.setattr(settings_mod, "USER_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(settings_mod, "SETTINGS_FILE", settings_dir / "settings.yaml")
    monkeypatch.setattr(
        settings_mod, "USER_KEY_PATH", encryption_dir / "encryption.key"
    )

    # Reset encryption manager state
    # pylint: disable=protected-access
    # Direct singleton access needed for test isolation
    encryption_mod.EncryptionManager._instance = None
    encryption_mod.EncryptionManager._key_path = None

    # Clear security state
    sqlcipher_mod.clear_cached_passphrase()
