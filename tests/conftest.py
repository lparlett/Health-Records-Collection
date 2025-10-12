import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
import services.providers as provider_service
from db.schema import ensure_schema


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
    cursor.execute(
        """
        INSERT INTO data_source (
            original_filename,
            ingested_at,
            file_sha256,
            source_archive
        ) VALUES (?, ?, ?, ?)
        """,
        ("sample.xml", "2025-10-12T00:00:00Z", "hash-sample", "archive.zip"),
    )
    schema_conn.commit()
    return int(cursor.lastrowid)


@pytest.fixture(autouse=True)
def clear_provider_cache() -> None:
    """Reset provider cache between tests to avoid cross-connection leakage."""
    provider_service._PROVIDER_CACHE.clear()
