from __future__ import annotations

import sqlite3

import pytest

from services.allergies import insert_allergies


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Allergy", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


@pytest.mark.usefixtures("schema_conn")
def test_insert_allergies_inserts_and_updates(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)

    payload = {
        "substance": "Peanuts",
        "substance_code": "256349002",
        "status": "active",
        "onset": "20241001",
        "reaction": "Hives",
        "severity": "Mild",
        "provider": "Dr Allergy Tester",
        "data_source_id": data_source_id,
        "source_allergy_id": "ALLERGY-1",
    }

    inserted, updated = insert_allergies(schema_conn, patient_id, [payload])
    assert inserted == 1
    assert updated == 0

    row = schema_conn.execute(
        """
        SELECT
            substance,
            substance_code,
            severity,
            reaction,
            provider_id,
            data_source_id
          FROM allergy
         WHERE patient_id = ?
        """,
        (patient_id,),
    ).fetchone()
    assert row is not None
    substance, substance_code, severity, reaction, provider_id, stored_source = row
    assert substance == "Peanuts"
    assert substance_code == "256349002"
    assert severity == "Mild"
    assert reaction == "Hives"
    assert provider_id is not None
    assert stored_source == data_source_id

    new_source = schema_conn.execute(
        """
        INSERT INTO data_source (original_filename, ingested_at, file_sha256)
        VALUES (?, ?, ?)
        """,
        ("allergy.xml", "2025-10-19T00:00:00Z", "hash-allergy"),
    ).lastrowid
    schema_conn.commit()

    update_payload = {
        **payload,
        "severity": "Severe",
        "reaction": "Anaphylaxis",
        "criticality": "High",
        "notes": "Carry epinephrine autoinjector",
        "data_source_id": int(new_source),
    }

    inserted_again, updated_again = insert_allergies(
        schema_conn,
        patient_id,
        [update_payload],
    )
    assert inserted_again == 0
    assert updated_again == 1

    updated_row = schema_conn.execute(
        """
        SELECT severity, reaction, criticality, notes, data_source_id
          FROM allergy
         WHERE patient_id = ?
        """,
        (patient_id,),
    ).fetchone()
    assert updated_row == (
        "Severe",
        "Anaphylaxis",
        "High",
        "Carry epinephrine autoinjector",
        int(new_source),
    )

    count = schema_conn.execute(
        "SELECT COUNT(*) FROM allergy WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()[0]
    assert count == 1

