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
from dataclasses import dataclass
from typing import Optional

__all__ = ["upsert_data_source", "link_attachment"]

logger = logging.getLogger(__name__)


@dataclass
class NormalizedMetadata:
    """Structured metadata fields for a data source record."""

    document_created: Optional[str]
    repository_unique_id: Optional[str]
    document_hash: Optional[str]
    document_size: Optional[int]
    author_institution: Optional[str]
    attachment_id: Optional[int]


def upsert_data_source(
    conn: sqlite3.Connection,
    file_path: Path,
    *,
    archive_id: Optional[int] = None,
    metadata: Optional[dict[str, object]] = None,
) -> int:
    """Ensure provenance metadata exists for an ingested CCD artifact.

    Args:
        conn: Active SQLite connection with foreign keys enabled.
        file_path: Path to the CCD XML file being persisted.
        archive_id: Optional ingested_archive primary key for the containing archive.
        metadata: Optional additional metadata dictionary with any of the
            following keys:
            - document_created: str | None
            - repository_unique_id: str | None
            - document_hash: str | None
            - document_size: int | None
            - author_institution: str | None
            - attachment_id: int | None

    Returns:
        int: The primary key of the corresponding `data_source` row.

    Raises:
        sqlite3.DatabaseError: If persistence fails.
        OSError: If the file cannot be read to compute its hash.
    """
    file_sha256 = _compute_file_hash(file_path)
    ingested_at = _current_ingested_timestamp()
    curated_archive_id = _coerce_optional_int(archive_id)
    normalized_metadata = _normalize_metadata(metadata or {})

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO data_source (
            original_filename,
            ingested_at,
            file_sha256,
            source_archive_id,
            document_created,
            repository_unique_id,
            document_hash,
            document_size,
            author_institution,
            attachment_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_sha256) DO UPDATE SET
            original_filename = excluded.original_filename,
            source_archive_id = COALESCE(
                excluded.source_archive_id, data_source.source_archive_id
            ),
            document_created = COALESCE(
                excluded.document_created, data_source.document_created
            ),
            repository_unique_id = COALESCE(
                excluded.repository_unique_id, data_source.repository_unique_id
            ),
            document_hash = COALESCE(excluded.document_hash, data_source.document_hash),
            document_size = COALESCE(excluded.document_size, data_source.document_size),
            author_institution = COALESCE(
                excluded.author_institution, data_source.author_institution
            ),
            attachment_id = COALESCE(data_source.attachment_id, excluded.attachment_id)
        """,
        (
            file_path.name,
            ingested_at,
            file_sha256,
            curated_archive_id,
            normalized_metadata.document_created,
            normalized_metadata.repository_unique_id,
            normalized_metadata.document_hash,
            normalized_metadata.document_size,
            normalized_metadata.author_institution,
            normalized_metadata.attachment_id,
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
            f"Unable to link attachment {attachment_id} to "
            f"data_source {data_source_id}."
        )
    conn.commit()


def _compute_file_hash(file_path: Path) -> str:
    """Return SHA-256 hash of the file contents."""
    try:
        file_bytes = file_path.read_bytes()
    except OSError as exc:
        logger.warning("Unable to read %s for provenance: %s", file_path, exc)
        raise
    return hashlib.sha256(file_bytes).hexdigest()


def _current_ingested_timestamp() -> str:
    """Return the current UTC timestamp formatted for storage."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_metadata(raw: dict[str, object]) -> NormalizedMetadata:
    """Return sanitized metadata fields."""
    return NormalizedMetadata(
        document_created=_optional_str(raw.get("document_created")),
        repository_unique_id=_optional_str(raw.get("repository_unique_id")),
        document_hash=_optional_str(raw.get("document_hash")),
        document_size=_coerce_optional_int(raw.get("document_size")),
        author_institution=_optional_str(raw.get("author_institution")),
        attachment_id=_coerce_optional_int(raw.get("attachment_id")),
    )


def _optional_str(value: object) -> Optional[str]:
    """Return a stripped string or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_int(value: object) -> Optional[int]:
    """Return integer value when possible; otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
