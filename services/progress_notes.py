"""Progress note ingestion helpers."""
from __future__ import annotations

import hashlib
import sqlite3
from typing import List, Optional, Tuple

from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_progress_notes"]


def _hash_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def insert_progress_notes(
    conn: sqlite3.Connection,
    patient_id: int,
    notes: List[dict],
) -> Tuple[int, int]:
    """Insert progress notes and report inserted versus duplicate counts."""
    if not notes:
        return 0, 0

    cur = conn.cursor()
    inserted = 0
    duplicates = 0

    for note in notes:
        raw_text = (note.get("text") or "").strip()
        if not raw_text:
            continue

        note_hash = _hash_text(raw_text)
        provider_name = note.get("provider")
        provider_id: Optional[int] = None
        if provider_name:
            provider_id = get_or_create_provider(conn, provider_name)

        encounter_hint = note.get("encounter_date") or note.get("note_datetime")
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=encounter_hint,
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=note.get("encounter_source_id"),
        )

        title = (note.get("title") or "").strip() or None
        note_datetime = note.get("note_datetime")
        source_note_id = (note.get("source_id") or "").strip() or None

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
