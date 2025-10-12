from __future__ import annotations

import sqlite3

from services.conditions import insert_conditions


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Condition", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_insert_conditions_sets_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    insert_conditions(
        schema_conn,
        patient_id,
        [
            {
                "name": "Hypertension",
                "start": "2024-01-01",
                "status": "active",
                "provider": "Example Clinician",
                "data_source_id": data_source_id,
            }
        ],
    )

    row = schema_conn.execute(
        "SELECT data_source_id FROM condition WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (data_source_id,)


def test_insert_conditions_updates_existing_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)

    new_source = schema_conn.execute(
        """
        INSERT INTO data_source (original_filename, ingested_at, file_sha256)
        VALUES (?, ?, ?)
        """,
        ("condition.xml", "2025-10-12T00:00:03Z", "hash-cond"),
    ).lastrowid
    schema_conn.commit()

    payload = {
        "name": "Hypertension",
        "start": "2024-01-01",
        "status": "active",
        "provider": "Example Clinician",
        "data_source_id": data_source_id,
    }
    assert schema_conn.execute(
        "SELECT COUNT(*) FROM data_source"
    ).fetchone()[0] >= 1
    insert_conditions(schema_conn, patient_id, [payload])

    payload["data_source_id"] = new_source
    insert_conditions(schema_conn, patient_id, [payload])

    row = schema_conn.execute(
        "SELECT data_source_id FROM condition WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (new_source,)
