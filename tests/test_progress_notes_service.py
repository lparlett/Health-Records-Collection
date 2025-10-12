from __future__ import annotations

import sqlite3

from services.progress_notes import insert_progress_notes


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Note", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_insert_progress_notes_sets_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    inserted, duplicates = insert_progress_notes(
        schema_conn,
        patient_id,
        [
            {
                "title": "Progress Note",
                "note_datetime": "2024-03-10T10:00:00",
                "text": "Patient is recovering as expected.",
                "provider": "Example Clinician",
                "data_source_id": data_source_id,
            }
        ],
    )
    assert inserted == 1
    assert duplicates == 0

    row = schema_conn.execute(
        "SELECT data_source_id FROM progress_note WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (data_source_id,)


def test_insert_progress_notes_updates_duplicate_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    new_source = schema_conn.execute(
        """
        INSERT INTO data_source (original_filename, ingested_at, file_sha256)
        VALUES (?, ?, ?)
        """,
        ("note.xml", "2025-10-12T00:00:06Z", "hash-note"),
    ).lastrowid
    schema_conn.commit()

    payload = {
        "title": "Progress Note",
        "note_datetime": "2024-03-10T10:00:00",
        "text": "Patient is recovering as expected.",
        "provider": "Example Clinician",
        "data_source_id": None,
    }
    insert_progress_notes(schema_conn, patient_id, [payload])

    payload["data_source_id"] = new_source
    inserted, duplicates = insert_progress_notes(schema_conn, patient_id, [payload])
    assert inserted == 0
    assert duplicates == 1

    row = schema_conn.execute(
        "SELECT data_source_id FROM progress_note WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (new_source,)
