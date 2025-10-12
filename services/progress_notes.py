# Purpose: Persist progress note narratives into the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Progress note ingestion helpers."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Mapping, Sequence, Tuple

from services.common import clean_str
from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_progress_notes"]


def _hash_text(value: str) -> str:
    """Return a SHA1 hash for duplicate detection."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def insert_progress_notes(
    conn: sqlite3.Connection,
    patient_id: int,
    notes: Sequence[Mapping[str, object]],
) -> Tuple[int, int]:
    """Insert progress notes and report inserted versus duplicate counts.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the note.
        notes: Sequence of parsed progress note dictionaries.

    Returns:
        Tuple[int, int]: Number of inserted notes and number of duplicates.
    """
    if not notes:
        return 0, 0

    cur = conn.cursor()
    inserted = 0
    duplicates = 0

    for note in notes:
        raw_text = clean_str(note.get("text"))
        if not raw_text:
            continue

        note_hash = _hash_text(raw_text)
        provider_name = clean_str(note.get("provider"))
        provider_id = get_or_create_provider(conn, provider_name) if provider_name else None

        encounter_hint = (
            clean_str(note.get("encounter_date"))
            or clean_str(note.get("note_datetime"))
        )
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=encounter_hint,
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=clean_str(note.get("encounter_source_id")),
        )

        title = clean_str(note.get("title"))
        note_datetime = clean_str(note.get("note_datetime"))
        source_note_id = clean_str(note.get("source_id"))

        cur.execute(
            """
            INSERT OR IGNORE INTO progress_note (
                patient_id,
                encounter_id,
                provider_id,
                note_title,
                note_datetime,
                note_text,
                note_hash,
                source_note_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                encounter_id,
                provider_id,
                title,
                note_datetime,
                raw_text,
                note_hash,
                source_note_id,
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            duplicates += 1

    conn.commit()
    return inserted, duplicates
