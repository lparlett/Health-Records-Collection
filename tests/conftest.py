import hashlib
import sqlite3
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import services.providers as provider_service
from db.schema import ensure_schema
import settings


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
def data_source_id(schema_conn: sqlite3.Connection) -> int:
    """Insert a reusable data_source row for tests that need a valid foreign key."""
    cursor = schema_conn.cursor()
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
    archive_id = int(cursor.lastrowid)
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
    schema_conn.commit()
    return int(cursor.lastrowid)


@pytest.fixture(autouse=True)
def clear_provider_cache() -> None:
    """Reset provider cache between tests to avoid cross-connection leakage."""
    provider_service._PROVIDER_CACHE.clear()


@pytest.fixture(autouse=True)
def isolate_user_settings(monkeypatch, tmp_path_factory) -> None:
    """Ensure user settings and encryption artifacts use a temp directory during tests."""
    from importlib import import_module

    settings = import_module("settings")
    encryption_module = import_module("security.encryption")
    sqlcipher_support = import_module("security.sqlcipher_support")

    settings_dir = tmp_path_factory.mktemp("settings")
    monkeypatch.setattr(settings, "USER_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(settings, "SETTINGS_FILE", settings_dir / "settings.yaml")
    encryption_module._MANAGER = None
    sqlcipher_support.clear_cached_passphrase()
