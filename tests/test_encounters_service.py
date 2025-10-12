from __future__ import annotations

import sqlite3

from services.encounters import insert_encounters


def _insert_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        INSERT INTO patient (
            given_name,
            family_name
        ) VALUES (?, ?)
        """,
        ("Test", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_insert_encounters_persists_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _insert_patient(schema_conn)

    insert_encounters(
        schema_conn,
        patient_id,
        [
            {
                "start": "20240102",
                "source_id": "enc-1",
                "type": "AMB",
                "notes": "Initial visit",
                "provider": "Example Clinic",
                "data_source_id": data_source_id,
            }
        ],
    )

    row = schema_conn.execute(
        "SELECT data_source_id FROM encounter WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (data_source_id,)


def test_insert_encounters_updates_duplicate_provenance(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _insert_patient(schema_conn)
    new_source = schema_conn.execute(
        """
        INSERT INTO data_source (original_filename, ingested_at, file_sha256)
        VALUES (?, ?, ?)
        """,
        ("encounter-2.xml", "2025-10-12T00:00:02Z", "hash-enc-2"),
    ).lastrowid
    schema_conn.commit()

    payload = {
        "start": "20240102",
        "source_id": "enc-dup",
        "type": "AMB",
        "provider": "Example Clinic",
        "data_source_id": data_source_id,
    }
    insert_encounters(schema_conn, patient_id, [payload])

    payload["data_source_id"] = new_source
    insert_encounters(schema_conn, patient_id, [payload])

    row = schema_conn.execute(
        """
        SELECT data_source_id
          FROM encounter
         WHERE patient_id = ?
           AND source_encounter_id = ?
        """,
        (patient_id, "enc-dup"),
    ).fetchone()
    assert row == (new_source,)
