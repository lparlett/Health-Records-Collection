from __future__ import annotations

import sqlite3

from services.medications import insert_medications


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Medication", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_insert_medications_sets_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    duplicates = insert_medications(
        schema_conn,
        patient_id,
        [
            {
                "name": "Lisinopril",
                "dose": "10 mg",
                "route": "oral",
                "frequency": "daily",
                "start": "2024-01-01",
                "status": "active",
                "data_source_id": data_source_id,
            }
        ],
    )
    assert duplicates == 0
    row = schema_conn.execute(
        "SELECT data_source_id FROM medication WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (data_source_id,)


def test_insert_medications_updates_existing(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    new_source = schema_conn.execute(
        """
        INSERT INTO data_source (original_filename, ingested_at, file_sha256)
        VALUES (?, ?, ?)
        """,
        ("medication.xml", "2025-10-12T00:00:05Z", "hash-med"),
    ).lastrowid
    schema_conn.commit()

    payload = {
        "name": "Lisinopril",
        "dose": "10 mg",
        "route": "oral",
        "frequency": "daily",
        "start": "2024-01-01",
        "status": "active",
        "data_source_id": None,
    }
    insert_medications(schema_conn, patient_id, [payload])

    payload["data_source_id"] = new_source
    duplicates = insert_medications(schema_conn, patient_id, [payload])
    assert duplicates == 1

    row = schema_conn.execute(
        """
        SELECT data_source_id
          FROM medication
         WHERE patient_id = ?
           AND name = ?
        """,
        (patient_id, "Lisinopril"),
    ).fetchone()
    assert row == (new_source,)
