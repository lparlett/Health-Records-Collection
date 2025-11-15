# Purpose: Persist progress note narratives into the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Progress note ingestion helpers."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from health_records_collection.services.common import clean_str, coerce_int
from health_records_collection.services.encounters import (
    EncounterLookup,
    find_encounter_id,
)
from health_records_collection.services.providers import get_or_create_provider

__all__ = ["insert_progress_notes"]


@dataclass
class ProgressNoteRecord:
    """Normalized progress note data ready for persistence."""

    patient_id: int
    encounter_id: Optional[int]
    provider_id: Optional[int]
    title: Optional[str]
    note_datetime: Optional[str]
    text: str
    note_hash: str
    source_note_id: Optional[str]
    data_source_id: Optional[int]


def _hash_text(value: str) -> str:
    """Return a SHA1 hash for duplicate detection."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
        record = _build_progress_note_record(conn, patient_id, note)
        if record is None:
            continue

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
                source_note_id,
                data_source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.patient_id,
                record.encounter_id,
                record.provider_id,
                record.title,
                record.note_datetime,
                record.text,
                record.note_hash,
                record.source_note_id,
                record.data_source_id,
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            duplicates += 1
            _update_existing_note(cur, record)

    conn.commit()
    return inserted, duplicates


def _build_progress_note_record(
    conn: sqlite3.Connection,
    patient_id: int,
    note: Mapping[str, object],
) -> Optional[ProgressNoteRecord]:
    """Normalize a raw note entry into a record."""
    raw_text = clean_str(note.get("text"))
    if not raw_text:
        return None

    note_hash = _hash_text(raw_text)
    provider_name = clean_str(note.get("provider"))
    provider_id = (
        get_or_create_provider(conn, provider_name) if provider_name else None
    )

    encounter_hint = clean_str(note.get("encounter_date")) or clean_str(
        note.get("note_datetime")
    )
    encounter_id = _resolve_encounter(
        conn,
        patient_id,
        encounter_hint,
        provider_name,
        provider_id,
    )

    return ProgressNoteRecord(
        patient_id=patient_id,
        encounter_id=encounter_id,
        provider_id=provider_id,
        title=clean_str(note.get("title")),
        note_datetime=clean_str(note.get("note_datetime")),
        text=raw_text,
        note_hash=note_hash,
        source_note_id=clean_str(note.get("source_id")),
        data_source_id=coerce_int(note.get("data_source_id")),
    )


def _resolve_encounter(
    conn: sqlite3.Connection,
    patient_id: int,
    encounter_hint: Optional[str],
    provider_name: Optional[str],
    provider_id: Optional[int],
) -> Optional[int]:
    """Return encounter id based on note metadata."""
    lookup = EncounterLookup(
        patient_id=patient_id,
        encounter_date=encounter_hint,
        provider_name=provider_name,
        provider_id=provider_id,
    )
    return find_encounter_id(conn, lookup)


def _update_existing_note(
    cur: sqlite3.Cursor,
    record: ProgressNoteRecord,
) -> None:
    """Update existing progress note with missing data source id."""
    if record.data_source_id is None:
        return

    cur.execute(
        """
        UPDATE progress_note
           SET data_source_id = COALESCE(data_source_id, ?)
         WHERE patient_id = ?
           AND COALESCE(encounter_id, -1) = COALESCE(?, -1)
           AND COALESCE(provider_id, -1) = COALESCE(?, -1)
           AND note_hash = ?
        """,
        (
            record.data_source_id,
            record.patient_id,
            record.encounter_id,
            record.provider_id,
            record.note_hash,
        ),
    )
