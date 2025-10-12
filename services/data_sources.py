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

__all__ = ["upsert_data_source", "link_attachment"]

logger = logging.getLogger(__name__)


def upsert_data_source(
    conn: sqlite3.Connection,
    file_path: Path,
    *,
    source_archive: Optional[str] = None,
    metadata: Optional[dict[str, object]] = None,
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
    metadata = metadata or {}
    document_created = metadata.get("document_created")
    repository_unique_id = metadata.get("repository_unique_id")
    document_hash = metadata.get("document_hash")
    document_size = metadata.get("document_size")
    author_institution = metadata.get("author_institution")
    attachment_metadata_id = metadata.get("attachment_id")
    if isinstance(document_size, str) and document_size.isdigit():
        document_size = int(document_size)
    elif not isinstance(document_size, int):
        document_size = None
    if attachment_metadata_id is not None:
        try:
            attachment_metadata_id = int(attachment_metadata_id)
        except (TypeError, ValueError):
            attachment_metadata_id = None

    document_created_text = (
        str(document_created) if document_created is not None else None
    )
    repository_unique_id_text = (
        str(repository_unique_id) if repository_unique_id is not None else None
    )
    document_hash_text = str(document_hash) if document_hash is not None else None
    author_institution_text = (
        str(author_institution) if author_institution is not None else None
    )

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO data_source (
            original_filename,
            ingested_at,
            file_sha256,
            source_archive,
            document_created,
            repository_unique_id,
            document_hash,
            document_size,
            author_institution,
            attachment_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_sha256) DO UPDATE SET
            original_filename = excluded.original_filename,
            source_archive = COALESCE(excluded.source_archive, data_source.source_archive),
            document_created = COALESCE(excluded.document_created, data_source.document_created),
            repository_unique_id = COALESCE(excluded.repository_unique_id, data_source.repository_unique_id),
            document_hash = COALESCE(excluded.document_hash, data_source.document_hash),
            document_size = COALESCE(excluded.document_size, data_source.document_size),
            author_institution = COALESCE(excluded.author_institution, data_source.author_institution),
            attachment_id = COALESCE(data_source.attachment_id, excluded.attachment_id)
        """,
        (
            file_path.name,
            ingested_at,
            file_sha256,
            curated_archive,
            document_created_text,
            repository_unique_id_text,
            document_hash_text,
            document_size,
            author_institution_text,
            attachment_metadata_id,
        ),
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


def link_attachment(
    conn: sqlite3.Connection,
    data_source_id: int,
    attachment_id: int,
) -> None:
    """Associate an attachment row with a data source."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE data_source
           SET attachment_id = ?
         WHERE id = ?
        """,
        (attachment_id, data_source_id),
    )
    if cur.rowcount != 1:
        raise sqlite3.DatabaseError(
            f"Unable to link attachment {attachment_id} to data_source {data_source_id}."
        )
    conn.commit()
