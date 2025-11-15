# Purpose: Persist raw attachment references for CCD documents.
# Author: Codex assistant + Lauren
# Date: 2025-10-12
# Related tests: tests/test_attachments_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Attachment persistence helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, TypedDict

from health_records_collection.db.utils import execute_update
from health_records_collection.services.common import (
    UpdateFieldSpec,
    build_updates_from_specs,
    clean_str,
    value_is_not_none,
)

__all__ = ["upsert_attachment"]


class AttachmentRecord(TypedDict, total=False):
    """Normalized attachment field values."""

    data_source_id: int
    mime_type: Optional[str]
    description: Optional[str]


ATTACHMENT_UPDATE_SPECS: tuple[UpdateFieldSpec, ...] = (
    UpdateFieldSpec("data_source_id", "data_source_id", 1, 0, value_is_not_none),
    UpdateFieldSpec("mime_type", "mime_type", 2, ""),
    UpdateFieldSpec("description", "description", 3, ""),
)


def upsert_attachment(
    conn: sqlite3.Connection,
    *,
    patient_id: int,
    data_source_id: int,
    file_path: Path,
    mime_type: Optional[str],
    description: Optional[str] = None,
) -> int:
    """Insert or update an attachment row for a CCD document."""
    normalized_path = _normalize_file_path(file_path)
    record = _build_record(data_source_id, mime_type, description)

    cur = conn.cursor()
    existing = _find_existing_attachment(cur, patient_id, normalized_path)
    if existing:
        attachment_id = existing[0]
        updates, params = build_updates_from_specs(
            record,
            existing,
            ATTACHMENT_UPDATE_SPECS,
        )
        if execute_update(cur, "attachment", updates, params, attachment_id):
            conn.commit()
        return attachment_id

    attachment_id = _insert_attachment(
        cur,
        patient_id=patient_id,
        normalized_path=normalized_path,
        record=record,
    )
    conn.commit()
    return attachment_id


def _normalize_file_path(file_path: Path) -> str:
    """Return a sanitized string path for the attachment."""
    normalized_path = clean_str(str(file_path))
    if normalized_path is None:
        raise ValueError("file_path must resolve to a non-empty string.")
    return normalized_path


def _build_record(
    data_source_id: int,
    mime_type: Optional[str],
    description: Optional[str],
) -> AttachmentRecord:
    """Return normalized attachment field values."""
    return {
        "data_source_id": data_source_id,
        "mime_type": clean_str(mime_type),
        "description": clean_str(description),
    }


def _find_existing_attachment(
    cur: sqlite3.Cursor,
    patient_id: int,
    normalized_path: str,
) -> Optional[tuple[int, Optional[int], Optional[str], Optional[str]]]:
    """Return an existing attachment row if present."""
    cur.execute(
        """
        SELECT id, data_source_id, mime_type, description
          FROM attachment
         WHERE patient_id = ?
           AND file_path = ?
        """,
        (patient_id, normalized_path),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return int(row[0]), row[1], row[2], row[3]


def _insert_attachment(
    cur: sqlite3.Cursor,
    *,
    patient_id: int,
    normalized_path: str,
    record: AttachmentRecord,
) -> int:
    """Insert a new attachment row and return its primary key."""
    cur.execute(
        """
        INSERT INTO attachment (
            patient_id,
            file_path,
            mime_type,
            description,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            patient_id,
            normalized_path,
            record.get("mime_type"),
            record.get("description"),
            record.get("data_source_id"),
        ),
    )
    attachment_id = cur.lastrowid
    if attachment_id is None:
        raise sqlite3.DatabaseError("Failed to insert attachment; lastrowid is None.")
    return int(attachment_id)
