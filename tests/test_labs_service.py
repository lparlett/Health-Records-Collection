from __future__ import annotations

import sqlite3

from services.labs import insert_labs


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Lab", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_insert_labs_sets_data_source(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)

    insert_labs(
        schema_conn,
        patient_id,
        [
            {
                "test_name": "Complete Blood Count",
                "loinc": "58410-2",
                "value": "12.5",
                "unit": "g/dL",
                "date": "2024-02-01",
                "data_source_id": data_source_id,
            }
        ],
    )

    row = schema_conn.execute(
        "SELECT data_source_id FROM lab_result WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    assert row == (data_source_id,)
