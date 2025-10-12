# Purpose: Persist raw attachment references for CCD documents.
# Author: Codex assistant + Lauren
# Date: 2025-10-12
# Related tests: tests/test_attachments_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Attachment persistence helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from services.common import clean_str

__all__ = ["upsert_attachment"]


def upsert_attachment(
    conn: sqlite3.Connection,
    *,
    patient_id: int,
    data_source_id: int,
    file_path: Path,
    mime_type: Optional[str],
    description: Optional[str] = None,
) -> int:
    """Insert or update an attachment row for a CCD document.

    Args:
        conn: Active SQLite connection.
        patient_id: Patient owning the attachment.
        data_source_id: Provenance identifier for the document.
        file_path: Path to the underlying document on disk.
        mime_type: Best-effort MIME type for the document.
        description: Optional human readable description.

    Returns:
        int: Primary key of the attachment row.
    """
    normalized_path = clean_str(str(file_path))
    if normalized_path is None:
        raise ValueError("file_path must resolve to a non-empty string.")

    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, data_source_id, mime_type, description
          FROM attachment
         WHERE patient_id = ?
           AND file_path = ?
        """,
        (patient_id, normalized_path),
    )
    existing = cur.fetchone()
    if existing:
        attachment_id, existing_ds, existing_mime, existing_desc = existing
        updates: list[str] = []
        params: list[object] = []
        if data_source_id and (existing_ds or 0) != data_source_id:
            updates.append("data_source_id = ?")
            params.append(data_source_id)
        if mime_type and (existing_mime or "") != mime_type:
            updates.append("mime_type = ?")
            params.append(mime_type)
        normalized_desc = clean_str(description)
        if normalized_desc and (existing_desc or "") != normalized_desc:
            updates.append("description = ?")
            params.append(normalized_desc)
        if updates:
            params.append(attachment_id)
            cur.execute(
                f"UPDATE attachment SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        conn.commit()
        return int(attachment_id)

    normalized_desc = clean_str(description)
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
            clean_str(mime_type),
            normalized_desc,
            data_source_id,
        ),
    )
    conn.commit()
    attachment_id = cur.lastrowid
    if attachment_id is None:
        raise sqlite3.DatabaseError("Failed to insert attachment; lastrowid is None.")
    return int(attachment_id)
