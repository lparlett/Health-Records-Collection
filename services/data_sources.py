# Purpose: Persist CCD source metadata for ingestion provenance.
# Author: Codex assistant + Lauren
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Data source persistence helpers."""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

__all__ = ["upsert_data_source"]

logger = logging.getLogger(__name__)


def upsert_data_source(
    conn: sqlite3.Connection,
    file_path: Path,
    *,
    source_archive: Optional[str] = None,
) -> int:
    """Ensure provenance metadata exists for an ingested CCD artifact.

    Args:
        conn: Active SQLite connection with foreign keys enabled.
        file_path: Path to the CCD XML file being persisted.
        source_archive: Optional archive name that contained the CCD file.

    Returns:
        int: The primary key of the corresponding `data_source` row.

    Raises:
        sqlite3.DatabaseError: If persistence fails.
        OSError: If the file cannot be read to compute its hash.
    """
    try:
        file_bytes = file_path.read_bytes()
    except OSError as exc:
        logger.warning("Unable to read %s for provenance: %s", file_path, exc)
        raise

    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    ingested_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    curated_archive = source_archive or None
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO data_source (
            original_filename,
            ingested_at,
            file_sha256,
            source_archive
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(file_sha256) DO UPDATE SET
            original_filename = excluded.original_filename,
            source_archive = excluded.source_archive
        """,
        (file_path.name, ingested_at, file_sha256, curated_archive),
    )

    cur.execute(
        "SELECT id FROM data_source WHERE file_sha256 = ?",
        (file_sha256,),
    )
    row = cur.fetchone()
    if row is None:
        raise sqlite3.DatabaseError("Failed to persist data_source metadata.")

    conn.commit()
    return int(row[0])
