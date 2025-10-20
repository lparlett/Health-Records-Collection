from __future__ import annotations

import sqlite3

from services.insurance import upsert_insurance


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Insurance", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_upsert_insurance_handles_insert_and_update(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    payload = {
        "payer_name": "Example Insurance",
        "plan_name": "Gold PPO",
        "coverage_type": "PPO",
        "member_id": "MEM123",
        "group_number": "GRP42",
        "status": "active",
        "payer_identifier": "758",
        "data_source_id": data_source_id,
    }

    inserted, updated = upsert_insurance(schema_conn, patient_id, [payload])
    assert inserted == 1
    assert updated == 0

    row = schema_conn.execute(
        """
        SELECT payer_name, plan_name, coverage_type, status, payer_identifier, data_source_id
          FROM insurance
         WHERE patient_id = ?
        """,
        (patient_id,),
    ).fetchone()
    assert row == (
        "Example Insurance",
        "Gold PPO",
        "PPO",
        "active",
        "758",
        data_source_id,
    )

    new_source = schema_conn.execute(
        """
        INSERT INTO data_source (original_filename, ingested_at, file_sha256)
        VALUES (?, ?, ?)
        """,
        ("insurance.xml", "2025-10-19T00:00:00Z", "hash-insurance"),
    ).lastrowid
    schema_conn.commit()

    update_payload = {
        **payload,
        "status": "inactive",
        "notes": "Coverage ended",
        "payer_identifier": "99999",
        "data_source_id": int(new_source),
    }
    inserted_again, updated_again = upsert_insurance(
        schema_conn,
        patient_id,
        [update_payload],
    )
    assert inserted_again == 0
    assert updated_again == 1

    updated_row = schema_conn.execute(
        """
        SELECT status, notes, payer_identifier, data_source_id
          FROM insurance
         WHERE patient_id = ?
        """,
        (patient_id,),
    ).fetchone()
    assert updated_row == ("inactive", "Coverage ended", "99999", int(new_source))

    count = schema_conn.execute(
        "SELECT COUNT(*) FROM insurance WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()[0]
    assert count == 1
