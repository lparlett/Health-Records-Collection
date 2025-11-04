# Purpose: Manage content-hash registry for ingested archives.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: tests/test_archives_service.py
# AI-assisted: Portions of this module were generated with AI assistance.
"""Helpers for tracking previously ingested CCD archives."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import sqlite3

__all__ = ["archive_was_ingested", "register_ingested_archive"]


def archive_was_ingested(
    conn: sqlite3.Connection,
    archive_sha256: str,
) -> Optional[Dict[str, Any]]:
    """Return registry details when an archive hash already exists."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id,
               archive_name,
               archive_sha256,
               first_ingested_at,
               last_ingested_at,
               ingest_count
          FROM ingested_archive
         WHERE archive_sha256 = ?
        """,
        (archive_sha256,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = [
        "id",
        "archive_name",
        "archive_sha256",
        "first_ingested_at",
        "last_ingested_at",
        "ingest_count",
    ]
    return dict(zip(keys, row))


def register_ingested_archive(
    conn: sqlite3.Connection,
    archive_name: str,
    archive_sha256: str,
) -> int:
    """Record or update the registry entry for an ingested archive."""
    timestamp = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, ingest_count
          FROM ingested_archive
         WHERE archive_sha256 = ?
        """,
        (archive_sha256,),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """
            INSERT INTO ingested_archive (
                archive_name,
                archive_sha256,
                first_ingested_at,
                last_ingested_at,
                ingest_count
            ) VALUES (?, ?, ?, ?, 1)
            """,
            (archive_name, archive_sha256, timestamp, timestamp),
        )
        if cur.lastrowid is None:
            msg = "Failed to insert archive row; lastrowid is None."
            raise sqlite3.DatabaseError(msg)
        archive_id = int(cur.lastrowid)
    else:
        archive_id = int(row[0])
        cur.execute(
            """
            UPDATE ingested_archive
               SET archive_name = ?,
                   last_ingested_at = ?,
                   ingest_count = ingest_count + 1
             WHERE archive_sha256 = ?
            """,
            (archive_name, timestamp, archive_sha256),
        )
    conn.commit()
    return archive_id
